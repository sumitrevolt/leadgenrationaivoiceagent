"""
Agent Talent Pool
Creates 992 specialized talents from 31 base agents using TypeSafe
"""
import logging
from typing import List, Dict, Any
from app.platform.team import STAFF
from app.platform.typesafe_integration import typesafe_choice

logger = logging.getLogger(__name__)

class AgentTalentPool:
    """Pool of 992 specialized talents from 31 agents"""
    
    def __init__(self):
        self.base_agents = STAFF
        self.talent_pool = []
        self._built = False
    
    def build_talent_pool(self) -> List[Dict[str, Any]]:
        """Build talent pool using TypeSafe for specialization"""
        if self._built:
            return self.talent_pool
        
        logger.info(f"Building talent pool from {len(self.base_agents)} base agents...")
        
        for agent_id, agent in self.base_agents.items():
            # Create 32 specializations per agent
            for i in range(32):
                talent = self._create_talent(agent_id, agent, i)
                self.talent_pool.append(talent)
        
        self._built = True
        logger.info(f"Talent pool built: {len(self.talent_pool)} talents")
        return self.talent_pool
    
    def _create_talent(self, agent_id: str, agent: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Create a single talent specialization using TypeSafe"""
        
        # Use TypeSafe to determine optimal specialization
        role = agent.get("role", "general")
        
        # Get role-specific criteria
        criteria = self._get_role_criteria(role)
        
        # Create state for TypeSafe
        state = {
            "role": role,
            "lane": agent.get("lane", "default"),
            "index": index,
            "total_specializations": 32,
            "agent_id": agent_id
        }
        
        # Ask TypeSafe for specialization
        question = f"What should {role} specialize in at level {index}?"
        
        try:
            result = typesafe_choice(question, state, criteria)
            specialization = result.value if result.success and result.value else f"{role}_specialist_{index}"
            confidence = result.confidence if result.success else 0.5
        except Exception as e:
            logger.warning(f"TypeSafe call failed for {agent_id}_{index}: {e}")
            specialization = f"{role}_fallback_{index}"
            confidence = 0.3
        
        # Calculate capacity based on specialization level
        capacity = self._calculate_capacity(agent, index)
        
        return {
            "id": f"{agent_id}_talent_{index}",
            "parent_agent": agent_id,
            "role": role,
            "specialization": specialization,
            "capability": self._map_to_capability(specialization),
            "capacity": capacity,
            "confidence": confidence,
            "status": "active"
        }
    
    def _get_role_criteria(self, role: str) -> Dict[str, str]:
        """Get TypeSafe criteria based on role"""
        criteria_map = {
            "sales": {
                "0": "Cold call expert",
                "1": "Warm lead specialist", 
                "2": "Enterprise closer",
                "3": "Relationship builder",
                "4": "Objection handler",
                "5": "Price negotiator",
                "6": "Demo presenter",
                "7": "Follow-up expert",
                "8": "Prospecting specialist",
                "9": "Closing expert"
            },
            "support": {
                "0": "Technical troubleshooter",
                "1": "Billing specialist",
                "2": "Onboarding expert",
                "3": "Escalation handler",
                "4": "Product specialist",
                "5": "Training coordinator",
                "6": "Quality assurance",
                "7": "Customer success",
                "8": "Retention specialist",
                "9": "Feedback analyst"
            },
            "marketing": {
                "0": "Content creator",
                "1": "SEO specialist",
                "2": "Social media expert",
                "3": "Email campaign manager",
                "4": "Lead generation",
                "5": "Brand strategist",
                "6": "Analytics specialist",
                "7": "Campaign optimizer",
                "8": "Creative director",
                "9": "Growth hacker"
            },
            "operations": {
                "0": "Process optimizer",
                "1": "Quality controller",
                "2": "Resource planner",
                "3": "Risk manager",
                "4": "Compliance officer",
                "5": "Vendor manager",
                "6": "Project coordinator",
                "7": "Performance analyst",
                "8": "Workflow automator",
                "9": "Efficiency expert"
            }
        }
        
        return criteria_map.get(role, {
            "0": "Generalist",
            "1": "Specialist",
            "2": "Expert",
            "3": "Senior expert",
            "4": "Lead",
            "5": "Manager",
            "6": "Director",
            "7": "VP",
            "8": "Head",
            "9": "Chief"
        })
    
    def _map_to_capability(self, specialization: str) -> str:
        """Map specialization to actual capability"""
        capability_map = {
            "cold_call_expert": "outbound_calling",
            "warm_lead_specialist": "follow_up",
            "enterprise_closer": "high_value_sales",
            "relationship_builder": "account_management",
            "objection_handler": "objection_handling",
            "price_negotiator": "pricing_strategy",
            "demo_presenter": "demo_delivery",
            "follow_up_expert": "nurture_sequences",
            "prospecting_specialist": "lead_generation",
            "closing_expert": "deal_closure",
            "technical_troubleshooter": "tech_support",
            "billing_specialist": "billing_support",
            "onboarding_expert": "customer_onboarding",
            "escalation_handler": "escalation_management",
            "product_specialist": "product_knowledge",
            "training_coordinator": "training_delivery",
            "quality_assurance": "quality_control",
            "customer_success": "customer_retention",
            "retention_specialist": "churn_prevention",
            "feedback_analyst": "feedback_collection",
            "content_creator": "content_generation",
            "seo_specialist": "seo_optimization",
            "social_media_expert": "social_management",
            "email_campaign_manager": "email_marketing",
            "lead_generation": "lead_generation",
            "brand_strategist": "brand_management",
            "analytics_specialist": "data_analytics",
            "campaign_optimizer": "campaign_optimization",
            "creative_director": "creative_direction",
            "growth_hacker": "growth_optimization",
            "process_optimizer": "process_optimization",
            "quality_controller": "quality_control",
            "resource_planner": "resource_allocation",
            "risk_manager": "risk_management",
            "compliance_officer": "compliance_management",
            "vendor_manager": "vendor_management",
            "project_coordinator": "project_management",
            "performance_analyst": "performance_tracking",
            "workflow_automator": "workflow_automation",
            "efficiency_expert": "efficiency_optimization"
        }
        
        return capability_map.get(specialization, "general")
    
    def _calculate_capacity(self, agent: Dict[str, Any], index: int) -> int:
        """Calculate daily capacity based on specialization level"""
        base_capacity = 50  # calls/tasks per day
        talent_multiplier = 1 + (index * 0.05)  # 5% boost per specialization level
        agent_boost = agent.get("expertise_level", 1.0)
        
        return int(base_capacity * talent_multiplier * agent_boost)
    
    def get_talent_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """Get all talents with specific capability"""
        return [t for t in self.talent_pool if t["capability"] == capability]
    
    def get_active_talents(self) -> List[Dict[str, Any]]:
        """Get all active talents"""
        return [t for t in self.talent_pool if t["status"] == "active"]
    
    def get_total_capacity(self) -> int:
        """Get total daily capacity across all talents"""
        return sum(t["capacity"] for t in self.talent_pool)
    
    def get_talent_stats(self) -> Dict[str, Any]:
        """Get statistics about talent pool"""
        return {
            "total_talents": len(self.talent_pool),
            "active_talents": len([t for t in self.talent_pool if t["status"] == "active"]),
            "total_capacity": self.get_total_capacity(),
            "avg_confidence": sum(t["confidence"] for t in self.talent_pool) / len(self.talent_pool) if self.talent_pool else 0,
            "by_role": self._stats_by_role(),
            "by_capability": self._stats_by_capability()
        }
    
    def _stats_by_role(self) -> Dict[str, int]:
        """Count talents by role"""
        stats = {}
        for talent in self.talent_pool:
            role = talent["role"]
            stats[role] = stats.get(role, 0) + 1
        return stats
    
    def _stats_by_capability(self) -> Dict[str, int]:
        """Count talents by capability"""
        stats = {}
        for talent in self.talent_pool:
            capability = talent["capability"]
            stats[capability] = stats.get(capability, 0) + 1
        return stats

# Singleton instance
_talent_pool = None

def get_talent_pool() -> AgentTalentPool:
    """Get or create talent pool singleton"""
    global _talent_pool
    if _talent_pool is None:
        _talent_pool = AgentTalentPool()
        _talent_pool.build_talent_pool()
    return _talent_pool

def get_talent_count() -> int:
    """Get total talent count"""
    return len(get_talent_pool().talent_pool)

def get_active_talent_count() -> int:
    """Get active talent count"""
    return len(get_talent_pool().get_active_talents())

def get_total_capacity() -> int:
    """Get total daily capacity"""
    return get_talent_pool().get_total_capacity()
