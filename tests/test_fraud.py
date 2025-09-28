from agent.fraud import simple_fraud_check
def test_flags():
    tx={'amount':6000,'counterparty':'X','hour':0}
    suspicious, details = simple_fraud_check(tx, known_counterparties=set())
    assert suspicious and 'large-amount' in details['flags']
