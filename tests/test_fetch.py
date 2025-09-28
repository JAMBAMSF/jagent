from agent.tools import map_symbol
def test_map_symbol():
    assert map_symbol('bonds') == 'BND'
    assert map_symbol('AAPL') == 'AAPL'
