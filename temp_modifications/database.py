import json
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from antigravity.config import settings
from antigravity.logging import get_logger

logger = get_logger("database")

Base = declarative_base()

class DBKline(Base):
    __tablename__ = 'klines'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    interval = Column(String)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    ts = Column(Integer) # Unix ms
    created_at = Column(DateTime, default=datetime.now)

class DBSignal(Base):
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True)
    strategy = Column(String)
    symbol = Column(String)
    type = Column(String)
    price = Column(Float)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.now)

class DBSentiment(Base):
    __tablename__ = 'sentiment'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    score = Column(Float)
    reasoning = Column(Text)
    model = Column(String)
    created_at = Column(DateTime, default=datetime.now)

class DBTrade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(String) # BUY / SELL
    price = Column(Float)
    quantity = Column(Float)
    value = Column(Float)
    pnl = Column(Float, default=0.0)
    strategy = Column(String)
    execution_type = Column(String) # REAL / PAPER
    created_at = Column(DateTime, default=datetime.now)

class DBPrediction(Base):
    __tablename__ = 'predictions'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    prediction_value = Column(Float)
    confidence = Column(Float)
    features = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

class DBRiskState(Base):
    __tablename__ = 'risk_state'
    id = Column(Integer, primary_key=True)
    daily_loss = Column(Float, default=0.0)
    last_reset_date = Column(String) # YYYY-MM-DD
    updated_at = Column(DateTime, default=datetime.now)

class DBStrategyState(Base):
    __tablename__ = 'strategy_state'
    id = Column(Integer, primary_key=True)
    strategy = Column(String)
    symbol = Column(String)
    state_json = Column(Text)
    updated_at = Column(DateTime, default=datetime.now)

class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = settings.DATABASE_URL
        self.engine = create_engine(db_path, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_kline(self, symbol, interval, o, h, l, c, v, ts):
        session = self.Session()
        try:
            k = DBKline(symbol=symbol, interval=interval, open=o, high=h, low=l, close=c, volume=v, ts=ts)
            session.add(k)
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    def get_strategy_state(self, strategy: str, symbol: str) -> dict:
        session = self.Session()
        try:
            state = session.query(DBStrategyState).filter_by(strategy=strategy, symbol=symbol).first()
            if state and state.state_json:
                return json.loads(state.state_json)
            return {}
        except Exception as e:
            logger.error("db_get_strategy_state_failed", error=str(e), strategy=strategy)
            return {}
        finally:
            session.close()

    def save_strategy_state(self, strategy: str, symbol: str, state: dict):
        session = self.Session()
        try:
            json_str = json.dumps(state)
            record = session.query(DBStrategyState).filter_by(strategy=strategy, symbol=symbol).first()
            if not record:
                record = DBStrategyState(strategy=strategy, symbol=symbol, state_json=json_str)
                session.add(record)
            else:
                record.state_json = json_str
                record.updated_at = datetime.now()
            session.commit()
        except Exception as e:
            logger.error("db_save_strategy_state_failed", error=str(e), strategy=strategy)
            session.rollback()
        finally:
            session.close()

    def get_risk_state(self):
        session = self.Session()
        try:
            # Singleton state, id=1
            state = session.query(DBRiskState).filter_by(id=1).first()
            if state:
                return {"daily_loss": state.daily_loss, "last_reset_date": state.last_reset_date}
            return None
        except Exception as e:
            logger.error("db_get_risk_state_failed", error=str(e))
            return None
        finally:
            session.close()

    def update_risk_state(self, daily_loss, last_reset_date):
        session = self.Session()
        try:
            state = session.query(DBRiskState).filter_by(id=1).first()
            if not state:
                state = DBRiskState(id=1, daily_loss=daily_loss, last_reset_date=last_reset_date, updated_at=datetime.now())
                session.add(state)
            else:
                state.daily_loss = daily_loss
                state.last_reset_date = last_reset_date
                state.updated_at = datetime.now()
            session.commit()
        except Exception as e:
            logger.error("db_update_risk_state_failed", error=str(e))
            session.rollback()
        finally:
            session.close()

    def save_signal(self, strategy, symbol, type_, price, reason):
        session = self.Session()
        try:
            s = DBSignal(strategy=strategy, symbol=symbol, type=type_, price=price, reason=reason)
            session.add(s)
            session.commit()
        except Exception as e:
            logger.error("db_save_signal_failed", error=str(e), strategy=strategy, symbol=symbol)
            session.rollback()
        finally:
            session.close()

    def save_sentiment(self, symbol, score, reasoning, model):
        session = self.Session()
        try:
            s = DBSentiment(symbol=symbol, score=score, reasoning=reasoning, model=model)
            session.add(s)
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()

    def save_trade(self, symbol, side, price, qty, val, strat, exec_type="PAPER", pnl=0.0):
        session = self.Session()
        try:
            t = DBTrade(symbol=symbol, side=side, price=price, quantity=qty, value=val, pnl=pnl, strategy=strat, execution_type=exec_type)
            session.add(t)
            session.commit()
        except Exception as e:
            logger.error("db_save_trade_failed", error=str(e), symbol=symbol, strategy=strat)
            session.rollback()
        finally:
            session.close()


    def save_prediction(self, symbol, prediction_value, confidence, features=None):
        session = self.Session()
        try:
            if features and isinstance(features, (dict, list)):
                features = json.dumps(features)

            p = DBPrediction(symbol=symbol, prediction_value=prediction_value, confidence=confidence, features=features)
            session.add(p)
            session.commit()
        except Exception as e:
            logger.error("db_save_prediction_failed", error=str(e), symbol=symbol)
            session.rollback()
        finally:
            session.close()

db = Database()
