import os
from datetime import datetime
from .metrics import metrics
from .logging import get_logger

logger = get_logger("alerts")

ALERTS_FILE = "/app/storage/alerts.log"
ALERT_THRESHOLDS = {
    'error_110007_rate': 10,
    'execution_failure_rate': 0.2,
}

def check_alerts():
    m = metrics.get_metrics()
    alerts = []
    
    error_110007 = m['counters'].get('api_error_110007', 0)
    if error_110007 > ALERT_THRESHOLDS['error_110007_rate']:
        alerts.append({
            'timestamp': datetime.now().isoformat(),
            'level': 'WARNING',
            'metric': 'error_110007_rate',
            'value': error_110007,
            'threshold': ALERT_THRESHOLDS['error_110007_rate'],
            'message': f"High 110007 error rate: {error_110007}/hour"
        })
    
    total_executions = m['counters'].get('execution_total', 0)
    failed_executions = m['counters'].get('execution_errors', 0)
    if total_executions > 0:
        failure_rate = failed_executions / total_executions
        if failure_rate > ALERT_THRESHOLDS['execution_failure_rate']:
            alerts.append({
                'timestamp': datetime.now().isoformat(),
                'level': 'CRITICAL',
                'metric': 'execution_failure_rate',
                'value': f"{failure_rate:.2%}",
                'threshold': f"{ALERT_THRESHOLDS['execution_failure_rate']:.0%}",
                'message': f"High execution failure rate: {failed_executions}/{total_executions}"
            })
    
    if alerts:
        with open(ALERTS_FILE, 'a') as f:
            for alert in alerts:
                f.write(f"{alert['timestamp']} | {alert['level']} | {alert['metric']} = {alert['value']} (threshold: {alert['threshold']}) | {alert['message']}\n")
                logger.warning("alert_triggered", **alert)
    
    return alerts
