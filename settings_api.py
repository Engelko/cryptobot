import os
import json
import asyncio
import docker
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn

from antigravity.profiles import (
    get_current_profile, 
    save_profile, 
    get_all_profiles,
    apply_profile_to_settings,
    PROFILES
)
from antigravity.logging import get_logger

logger = get_logger("settings_api")

try:
    docker_client = docker.from_env()
except Exception as e:
    logger.warning("docker_client_init_failed", error=str(e))
    docker_client = None

app = FastAPI(title="CryptoBot Settings API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SETTINGS_FILE = "storage/bot_control.json"

class ProfileSwitchRequest(BaseModel):
    profile: str
    restart: bool = True

class CustomSettingsRequest(BaseModel):
    max_spread: Optional[float] = None
    max_leverage: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_position_size: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None

@app.get("/")
async def root():
    return {"status": "ok", "service": "cryptobot-settings-api"}

@app.get("/api/profiles")
async def list_profiles():
    profiles = get_all_profiles()
    current = get_current_profile()
    return {
        "current": {
            "key": [k for k, v in PROFILES.items() if v.name == current.name][0] if current else "testnet",
            "name": current.name,
            "is_testnet": current.is_testnet
        },
        "available": profiles
    }

@app.get("/api/profile/current")
async def get_current():
    profile = get_current_profile()
    return {
        "name": profile.name,
        "description": profile.description,
        "is_testnet": profile.is_testnet,
        "params": {
            "max_spread": profile.max_spread,
            "max_leverage": profile.max_leverage,
            "max_daily_loss": profile.max_daily_loss,
            "max_position_size": profile.max_position_size,
            "max_single_trade_loss": profile.max_single_trade_loss,
            "stop_loss_pct": profile.stop_loss_pct,
            "take_profit_pct": profile.take_profit_pct,
            "trailing_stop_trigger": profile.trailing_stop_trigger,
            "min_hold_time": profile.min_hold_time,
            "cooldown_after_loss": profile.cooldown_after_loss,
            "session_blacklist": profile.session_blacklist,
            "min_adx_entry": profile.min_adx_entry,
            "enable_spread_check": profile.enable_spread_check,
            "spread_multiplier": profile.spread_multiplier,
            "enable_spot_mode_for_volatile": profile.enable_spot_mode_for_volatile,
            "enable_regime_filter": profile.enable_regime_filter,
            "risk_per_trade": profile.risk_per_trade
        }
    }

@app.post("/api/profile/switch")
async def switch_profile(request: ProfileSwitchRequest):
    if request.profile not in PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown profile: {request.profile}")
    
    old_profile = get_current_profile()
    
    if not save_profile(request.profile):
        raise HTTPException(status_code=500, detail="Failed to save profile")
    
    new_profile = get_current_profile()
    
    logger.info("profile_switched", old=old_profile.name, new=new_profile.name)
    
    result = {
        "success": True,
        "old_profile": old_profile.name,
        "new_profile": new_profile.name,
        "restart_triggered": False
    }
    
    if request.restart:
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"action": "restart", "reason": "profile_switch"}, f)
            
            result["restart_triggered"] = True
            result["message"] = f"Profile switched to {new_profile.name}. Bot will restart in 5 seconds."
            
            asyncio.create_task(delayed_restart())
        except Exception as e:
            logger.error("restart_trigger_failed", error=str(e))
            result["message"] = f"Profile switched to {new_profile.name}. Manual restart required."
    
    return result

async def delayed_restart():
    await asyncio.sleep(5)
    logger.info("executing_restart")
    if docker_client:
        try:
            for container_name in ["antigravity-engine", "antigravity-dashboard", "antigravity-optimizer"]:
                try:
                    container = docker_client.containers.get(container_name)
                    container.restart()
                    logger.info("container_restarted", container=container_name)
                except Exception as e:
                    logger.error("container_restart_failed", container=container_name, error=str(e))
        except Exception as e:
            logger.error("restart_error", error=str(e))
    else:
        logger.error("docker_client_not_available")

@app.post("/api/settings/custom")
async def update_custom_settings(request: CustomSettingsRequest):
    profile = get_current_profile()
    
    updates = []
    if request.max_spread is not None:
        profile.max_spread = request.max_spread
        updates.append(f"max_spread={request.max_spread}")
    if request.max_leverage is not None:
        profile.max_leverage = request.max_leverage
        updates.append(f"max_leverage={request.max_leverage}")
    if request.max_daily_loss is not None:
        profile.max_daily_loss = request.max_daily_loss
        updates.append(f"max_daily_loss={request.max_daily_loss}")
    if request.max_position_size is not None:
        profile.max_position_size = request.max_position_size
        updates.append(f"max_position_size={request.max_position_size}")
    if request.stop_loss_pct is not None:
        profile.stop_loss_pct = request.stop_loss_pct
        updates.append(f"stop_loss_pct={request.stop_loss_pct}")
    if request.take_profit_pct is not None:
        profile.take_profit_pct = request.take_profit_pct
        updates.append(f"take_profit_pct={request.take_profit_pct}")
    
    apply_profile_to_settings()
    
    return {
        "success": True,
        "updates": updates,
        "message": f"Settings updated: {', '.join(updates)}"
    }

@app.post("/api/bot/restart")
async def restart_bot():
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"action": "restart", "reason": "manual"}, f)
        
        asyncio.create_task(delayed_restart())
        
        return {
            "success": True,
            "message": "Bot restart initiated. Please wait 10 seconds."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bot/status")
async def get_bot_status():
    if not docker_client:
        return {"containers": [], "healthy": False, "error": "Docker client not available"}
    
    try:
        containers = docker_client.containers.list(all=True, filters={"name": "antigravity"})
        result = []
        all_healthy = True
        
        for c in containers:
            status = c.status
            name = c.name
            result.append(f"{name}: {status}")
            if status != "running":
                all_healthy = False
        
        return {
            "containers": result,
            "healthy": all_healthy and len(result) > 0
        }
    except Exception as e:
        logger.error("bot_status_error", error=str(e))
        return {"containers": [], "healthy": False, "error": str(e)}

def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    run_api()
