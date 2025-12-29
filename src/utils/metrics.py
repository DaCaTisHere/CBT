"""Performance metrics tracking"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

class MetricsTracker:
    """Track bot performance metrics"""
    
    def __init__(self, filepath: str = "metrics.json"):
        self.filepath = Path(filepath)
        self.metrics = self._load()
    
    def _load(self) -> Dict:
        """Load metrics from file"""
        if self.filepath.exists():
            return json.loads(self.filepath.read_text())
        return {
            "start_date": datetime.utcnow().isoformat(),
            "total_runtime_hours": 0,
            "opportunities_detected": 0,
            "trades_simulated": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "daily_stats": []
        }
    
    def save(self):
        """Save metrics to file"""
        self.filepath.write_text(json.dumps(self.metrics, indent=2))
    
    def log_opportunity(self, symbol: str, source: str):
        """Log detected opportunity"""
        self.metrics["opportunities_detected"] += 1
        self.save()
    
    def log_trade(self, profit: float, win: bool):
        """Log simulated trade"""
        self.metrics["trades_simulated"] += 1
        if win:
            self.metrics["wins"] += 1
        else:
            self.metrics["losses"] += 1
        self.metrics["total_pnl"] += profit
        self.save()
    
    def get_win_rate(self) -> float:
        """Calculate win rate"""
        total = self.metrics["trades_simulated"]
        if total == 0:
            return 0.0
        return (self.metrics["wins"] / total) * 100
    
    def get_summary(self) -> str:
        """Get metrics summary"""
        wr = self.get_win_rate()
        return f"""
📊 PERFORMANCE METRICS
=====================
Runtime: {self.metrics['total_runtime_hours']:.1f}h
Opportunities: {self.metrics['opportunities_detected']}
Trades: {self.metrics['trades_simulated']}
Win Rate: {wr:.1f}%
Total PnL: ${self.metrics['total_pnl']:.2f}
"""

# Global tracker
tracker = MetricsTracker()

