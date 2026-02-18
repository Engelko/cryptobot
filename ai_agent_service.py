import os
import json
import yaml
import asyncio
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import requests
from dotenv import set_key
from antigravity.ai_client_generic import LLMClient
from antigravity.logging import configure_logging, get_logger
from antigravity.config import settings
from antigravity.profiles import apply_profile_to_settings

# Configure logging for the service
configure_logging()
logger = get_logger("ai_agent_service")

class AIAgentService:
    def __init__(self):
        self.db_path = "storage/data.db"
        self.strategies_yaml = "strategies.yaml"
        self.env_file = ".env"
        self.profile_file = "storage/current_profile.json"
        self.override_file = "storage/profile_overrides.json"
        self.settings_api_url = os.getenv("SETTINGS_API_URL", "http://settings-api:8080")

        self.interval_hours = int(os.getenv("AI_AGENT_INTERVAL_HOURS", "12"))
        self.dry_run = os.getenv("AI_DRY_RUN", "false").lower() == "true"

        # LLM Config
        self.provider = os.getenv("LLM_PROVIDER", "openai")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model_id = os.getenv("LLM_MODEL_ID", "gpt-4-turbo")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

        self.client = LLMClient(
            provider=self.provider,
            api_key=self.api_key,
            model_id=self.model_id,
            base_url=self.base_url,
            timeout=int(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024"))
        )

    async def run_once(self):
        logger.info("ai_agent_run_started", dry_run=self.dry_run)

        # 1. Aggregate Data
        data = self.aggregate_data()
        if not data:
            logger.error("data_aggregation_failed")
            return

        # 2. Call AI
        response_json = await self.call_ai(data)
        if not response_json:
            logger.error("ai_call_failed")
            return

        # 3. Apply Changes
        if self.dry_run:
            logger.info("dry_run_enabled_skipping_application", suggestion=response_json)
        else:
            await self.apply_configuration(response_json)

        logger.info("ai_agent_run_completed")

    def aggregate_data(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Timeframe
            stats_days = int(os.getenv("AI_STATS_DAYS", "7"))
            since_date = (datetime.now() - timedelta(days=stats_days)).strftime("%Y-%m-%d %H:%M:%S")

            # Market Snapshot
            market_snapshot = {}
            # Verify klines table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='klines'")
            if not cursor.fetchone():
                logger.warning("klines_table_not_found_skipping_market_snapshot")
            else:
                cursor.execute("SELECT symbol, regime, adx, volatility FROM market_regime")
                for row in cursor.fetchall():
                    market_snapshot[row['symbol']] = {
                        "regime": row['regime'],
                        "adx": row['adx'],
                        "volatility": row['volatility']
                    }

                # Latest prices and changes
                for symbol in market_snapshot:
                    cursor.execute("SELECT close FROM klines WHERE symbol = ? ORDER BY ts DESC LIMIT 2", (symbol,))
                    rows = rows = cursor.fetchall()
                    if len(rows) >= 1:
                        market_snapshot[symbol]["price"] = rows[0][0]
                    if len(rows) >= 2:
                        change = ((rows[0][0] - rows[1][0]) / rows[1][0]) * 100
                        market_snapshot[symbol]["change_24h_approx"] = change

                    # Simple S/R
                    cursor.execute("SELECT MIN(low), MAX(high) FROM klines WHERE symbol = ? AND created_at > ?", (symbol, since_date))
                    sr_row = cursor.fetchone()
                    if sr_row:
                        market_snapshot[symbol]["support"] = sr_row[0]
                        market_snapshot[symbol]["resistance"] = sr_row[1]

            # Strategy Stats
            strategy_stats = {}
            cursor.execute("""
                SELECT strategy,
                       SUM(pnl) as total_pnl,
                       COUNT(*) as trade_count,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                       AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                       AVG(CASE WHEN pnl < 0 THEN pnl ELSE NULL END) as avg_loss
                FROM trades
                WHERE created_at > ?
                GROUP BY strategy
            """, (since_date,))

            for row in cursor.fetchall():
                win_rate = (row['wins'] / row['trade_count']) if row['trade_count'] > 0 else 0
                rr = (abs(row['avg_win'] / row['avg_loss'])) if row['avg_loss'] and row['avg_loss'] != 0 else 0
                strategy_stats[row['strategy']] = {
                    "pnl": row['total_pnl'],
                    "trade_count": row['trade_count'],
                    "win_rate": win_rate,
                    "avg_win": row['avg_win'],
                    "avg_loss": row['avg_loss'],
                    "risk_reward": rr
                }

            # Risk Profile
            current_profile_name = "testnet"
            if os.path.exists(self.profile_file):
                with open(self.profile_file, "r") as f:
                    try:
                        current_profile_name = json.load(f).get("profile", "testnet")
                    except:
                        pass

            risk_profile = {
                "name": current_profile_name,
                "max_daily_loss": settings.MAX_DAILY_LOSS,
                "max_position_size": settings.MAX_POSITION_SIZE,
                "max_leverage": settings.MAX_LEVERAGE,
                "stop_loss_pct": settings.STOP_LOSS_PCT,
                "take_profit_pct": settings.TAKE_PROFIT_PCT,
                "session_blacklist": settings.SESSION_BLACKLIST
            }

            conn.close()

            return {
                "timeframe_hours": self.interval_hours,
                "market_snapshot": market_snapshot,
                "strategy_stats": strategy_stats,
                "risk_profile": risk_profile,
                "recent_issues": [],
                "constraints": {
                    "allow_profile_switch": True,
                    "allow_risk_tuning": True,
                    "max_param_change_pct": 30,
                    "allow_enable_disabled_strategies": False
                }
            }
        except Exception as e:
            logger.error("aggregation_error", error=str(e))
            return {}

    async def call_ai(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        system_prompt = self.get_system_prompt()
        user_prompt = json.dumps(data, indent=2)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        logger.info("ai_request_sent", model=self.model_id)
        response_text = await self.client.chat(messages)

        if not response_text:
            return None

        try:
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

            return json.loads(cleaned_text)
        except Exception as e:
            logger.error("ai_response_parse_error", error=str(e), raw_response=response_text)
            return None

    def get_system_prompt(self) -> str:
        if os.path.exists("AI_AGENT_SPEC.md"):
            with open("AI_AGENT_SPEC.md", "r") as f:
                content = f.read()
                if "BLOCK B" in content:
                    return content.split("BLOCK B")[1].split("====")[0].strip()
        return "You are an AI crypto market analyst. Propose config changes in JSON format."

    async def apply_configuration(self, plan: Dict[str, Any]):
        logger.info("applying_configuration")

        profile_changed = False
        strategies_changed = False
        env_changed = False

        # 1. Profile Switch
        target_profile = plan.get("target_profile")
        if target_profile:
            logger.info("switching_profile", target=target_profile)
            try:
                resp = requests.post(f"{self.settings_api_url}/api/profileswitch",
                                    json={"profile": target_profile, "restart": False})
                if resp.status_code == 200:
                    profile_changed = True
                else:
                    logger.error("profile_switch_failed", status=resp.status_code, text=resp.text)
            except Exception as e:
                logger.error("profile_switch_error", error=str(e))

        # 2. Risk Overrides
        risk_overrides = plan.get("risk_overrides", {})
        if risk_overrides:
            risk_param_map = {
                "maxdailyloss": "max_daily_loss",
                "maxpositionsize": "max_position_size",
                "maxsingletradeloss": "max_single_trade_loss",
                "stoplosspct": "stop_loss_pct",
                "takeprofitpct": "take_profit_pct",
                "maxleverage": "max_leverage",
                "riskpertrade": "risk_per_trade"
            }
            clean_overrides = {}
            for k, v in risk_overrides.items():
                if v is not None:
                    param_name = risk_param_map.get(k.lower(), k)
                    # SAFETY CAPS
                    if param_name == "risk_per_trade":
                         v = min(v, 0.05)
                    if param_name == "max_leverage":
                         v = min(v, settings.MAX_LEVERAGE)
                    clean_overrides[param_name] = v

            if clean_overrides:
                os.makedirs(os.path.dirname(self.override_file), exist_ok=True)
                with open(self.override_file, "w") as f:
                    json.dump(clean_overrides, f, indent=2)
                logger.info("risk_overrides_applied", overrides=clean_overrides)
                profile_changed = True

        # 3. Strategy Plan
        strategy_plan = plan.get("strategy_plan", [])
        if strategy_plan:
            if os.path.exists(self.strategies_yaml):
                with open(self.strategies_yaml, "r") as f:
                    config = yaml.safe_load(f)

                active_strategies = []
                name_map = {
                    "GoldenCross": "trend_following",
                    "BollingerRSI": "mean_reversion",
                    "BBSqueeze": "bb_squeeze",
                    "DynamicRiskLeverage": "dynamic_risk_leverage"
                }
                param_map = {
                    "fastperiod": "fast_period",
                    "slowperiod": "slow_period",
                    "riskpertrade": "risk_per_trade",
                    "bbperiod": "bb_period",
                    "bbstd": "bb_std",
                    "rsiperiod": "rsi_period",
                    "rsioverbought": "rsi_overbought",
                    "rsioversold": "rsi_oversold"
                }

                for item in strategy_plan:
                    name = item.get("name")
                    yaml_key = name_map.get(name)
                    if yaml_key and yaml_key in config['strategies']:
                        strat_cfg = config['strategies'][yaml_key]
                        if "enabled" in item:
                            strat_cfg["enabled"] = item["enabled"]
                        updates = item.get("param_updates", {})
                        for pk, pv in updates.items():
                            if pv is not None:
                                yaml_pk = param_map.get(pk.lower(), pk)
                                if yaml_pk == "risk_per_trade":
                                    pv = min(pv, 0.05)
                                if yaml_pk == "leverage":
                                    pv = min(pv, settings.MAX_LEVERAGE)
                                if yaml_pk in strat_cfg:
                                    strat_cfg[yaml_pk] = pv
                                else:
                                    logger.warning("unknown_strategy_param", strategy=name, param=pk)
                        if strat_cfg.get("enabled"):
                            active_strategies.append(name)
                        strategies_changed = True

                if strategies_changed:
                    with open(self.strategies_yaml, "w") as f:
                        yaml.dump(config, f, sort_keys=False)
                    logger.info("strategies_yaml_updated")
                    if active_strategies:
                        self.update_env("ACTIVESTRATEGIES", ",".join(active_strategies))
                        env_changed = True

        if profile_changed or strategies_changed or env_changed:
            logger.info("triggering_bot_restart")
            try:
                requests.post(f"{self.settings_api_url}/api/botrestart")
            except Exception as e:
                logger.error("restart_trigger_failed", error=str(e))

    def update_env(self, key: str, value: str):
        try:
            if not os.path.exists(self.env_file):
                with open(self.env_file, "w") as f:
                    pass
            set_key(self.env_file, key, value, quote_mode="never")
            logger.info("env_updated", key=key)
        except Exception as e:
            logger.error("env_update_error", key=key, error=str(e))

    async def main_loop(self):
        while True:
            try:
                await self.run_once()
            except Exception as e:
                logger.error("loop_error", error=str(e))
            logger.info("sleeping_until_next_run", hours=self.interval_hours)
            await asyncio.sleep(self.interval_hours * 3600)

if __name__ == "__main__":
    # Ensure settings are synced with current profile
    try:
        apply_profile_to_settings()
    except Exception as e:
        logger.error("settings_sync_failed", error=str(e))

    service = AIAgentService()
    asyncio.run(service.main_loop())
