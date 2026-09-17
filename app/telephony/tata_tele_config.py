"""
Tata Tele Channel Configuration
Manages 5 Tata Tele channels for outbound/inbound calls
"""
import os
import logging
from typing import Dict, List, Any
from datetime import time

logger = logging.getLogger(__name__)

class TataTeleConfig:
    """Configuration for Tata Tele 5 channels"""
    
    def __init__(self):
        self.channels = self._load_config()
        self.outbound_start = time(9, 0)  # 9 AM
        self.outbound_end = time(20, 0)   # 8 PM
        self.inbound_24_7 = True
    
    def _load_config(self) -> List[Dict[str, Any]]:
        """Load channel configuration"""
        # Default configuration for 5 channels
        channels = []
        
        for i in range(1, 6):
            channels.append({
                "id": f"tata_channel_{i}",
                "number": f"+9180698797{i:02d}",  # Example numbers
                "status": "active" if i == 1 else "pending",  # Channel 1 live, others pending
                "type": "trunk",
                "capacity_per_hour": 10,
                "daily_limit": 240,  # 10 calls/hour × 24 hours
                "outbound_enabled": True,
                "inbound_enabled": True,
                "products": self._get_products_for_channel(i)
            })
        
        return channels
    
    def _get_products_for_channel(self, channel_num: int) -> List[str]:
        """Assign products to channels"""
        product_map = {
            1: ["marketing_starter", "marketing_advanced"],  # LIVE
            2: ["voice_starter", "voice_band_a"],  # Coming
            3: ["marketing_advanced", "combo_starter"],  # Coming
            4: ["enterprise", "combo_pro"],  # Coming
            5: ["voice_band_b", "voice_band_c"]  # Coming
        }
        return product_map.get(channel_num, ["all"])
    
    def get_active_channels(self) -> List[Dict[str, Any]]:
        """Get all active channels"""
        return [c for c in self.channels if c["status"] == "active"]
    
    def get_pending_channels(self) -> List[Dict[str, Any]]:
        """Get pending channels (coming soon)"""
        return [c for c in self.channels if c["status"] == "pending"]
    
    def get_total_capacity(self) -> int:
        """Get total daily call capacity"""
        active = self.get_active_channels()
        return sum(c["daily_limit"] for c in active)
    
    def get_capacity_by_product(self) -> Dict[str, int]:
        """Get capacity breakdown by product"""
        capacity = {}
        for channel in self.get_active_channels():
            for product in channel["products"]:
                capacity[product] = capacity.get(product, 0) + channel["daily_limit"]
        return capacity
    
    def is_outbound_allowed(self) -> bool:
        """Check if outbound calls are allowed (based on time)"""
        from datetime import datetime
        now = datetime.now().time()
        return self.outbound_start <= now <= self.outbound_end
    
    def get_revenue_potential(self) -> Dict[str, Any]:
        """Calculate revenue potential from channels"""
        total_calls = self.get_total_capacity()
        conversion_rate = 0.05  # 5% conservative
        avg_order_value = 2990  # ₹2,990 blended ARPU
        
        daily_customers = int(total_calls * conversion_rate)
        daily_revenue = daily_customers * avg_order_value
        monthly_revenue = daily_revenue * 30
        
        return {
            "daily_calls": total_calls,
            "daily_customers": daily_customers,
            "daily_revenue": daily_revenue,
            "monthly_revenue": monthly_revenue,
            "conversion_rate": conversion_rate,
            "avg_order_value": avg_order_value
        }
    
    def update_channel_status(self, channel_id: str, status: str):
        """Update channel status (e.g., when new channel becomes live)"""
        for channel in self.channels:
            if channel["id"] == channel_id:
                channel["status"] = status
                logger.info(f"Updated channel {channel_id} status to {status}")
                return True
        return False

# Singleton instance
_tata_config = None

def get_tata_config() -> TataTeleConfig:
    """Get Tata Tele configuration singleton"""
    global _tata_config
    if _tata_config is None:
        _tata_config = TataTeleConfig()
    return _tata_config

def get_active_channel_count() -> int:
    """Get number of active channels"""
    return len(get_tata_config().get_active_channels())

def get_total_daily_capacity() -> int:
    """Get total daily call capacity"""
    return get_tata_config().get_total_capacity()

def get_revenue_potential() -> Dict[str, Any]:
    """Get revenue potential from channels"""
    return get_tata_config().get_revenue_potential()
