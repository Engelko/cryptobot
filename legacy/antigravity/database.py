import json
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from antigravity.config import settings

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
    created_at = Column(DateTime, default=datetime.utcnow)

class DBSignal(Base):
    __tablename__ = 'signals'
    id = Column(Integer, primary_key=True)
    strategy = Column(String)
    symbol = Column(String)
    type = Column(String)
    price = Column(Float)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBSentiment(Base):
    __tablename__ = 'sentiment'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    score = Column(Float)
    reasoning = Column(Text)
    model = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow)

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

    def save_signal(self, strategy, symbol, type_, price, reason):
        session = self.Session()
        try:
            s = DBSignal(strategy=strategy, symbol=symbol, type=type_, price=price, reason=reason)
            session.add(s)
            session.commit()
        except Exception as e:
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
            session.rollback()
        finally:
            session.close()

db = Database()
