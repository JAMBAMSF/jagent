import pandas as pd, numpy as np
from agent.portfolio import expected_return, portfolio_volatility, normalize_allocations
def test_basic_metrics():
    idx=pd.date_range('2024-01-01', periods=10, freq='B')
    df=pd.DataFrame({'AAA': np.linspace(100,110,10)}, index=idx)
    rets=df.pct_change().dropna(); w={'AAA':1.0}
    mu=expected_return(rets,w); vol=portfolio_volatility(rets,w)
    assert mu!=0 and vol>=0
def test_normalize():
    w=normalize_allocations({'A':2,'B':2}); assert abs(sum(w.values())-1.0)<1e-6
