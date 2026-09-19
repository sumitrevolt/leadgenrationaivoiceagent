"""31 Agent Bots with Enterprise Profiles.

Each agent has a name, role, skills, and performance tracking.
Follows the existing STAFF roster pattern from app/platform/team.py.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


_IST = timezone(timedelta(hours=5, minutes=30))


class AgentProfile(BaseModel):
    """Enterprise agent profile."""
    agent_id: str
    name: str
    role: str
    product: str  # "marketing" or "voice" or "platform"
    emoji: str
    duties: str
    schedule: str
    skills: list[str] = Field(default_factory=list)
    status: str = "idle"  # idle, working, offline
    last_active: Optional[str] = None
    tasks_completed_today: int = 0
    tasks_completed_total: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "product": self.product,
            "emoji": self.emoji,
            "duties": self.duties,
            "schedule": self.schedule,
            "skills": self.skills,
            "status": self.status,
            "last_active": self.last_active,
            "tasks_completed_today": self.tasks_completed_today,
            "tasks_completed_total": self.tasks_completed_total,
        }


# ============================================================================
# 31 AGENT PROFILES (mirrors existing STAFF roster)
# ============================================================================

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    # Platform agents (Boss/Manager)
    "manager": {
        "product": "platform",
        "name": "Boss",
        "emoji": "🧑‍💼",
        "title": "Manager (Supervisor)",
        "duties": "Kaam baantna — data/leads agents ko route karna (LangGraph), team coordination",
        "schedule": "On-demand (har /api/agents/run pe)",
        "skills": ["coordination", "routing", "supervision"],
    },
    # Voice agents (Swara, Ananya, Riya)
    "swara": {
        "product": "voice",
        "name": "Swara",
        "emoji": "📞",
        "title": "Telecaller",
        "duties": "End-customers ko call karna (phone + web demo), niche scripts se qualify karna, objections handle karna",
        "schedule": "On-demand (calls/demos)",
        "skills": ["calling", "qualification", "objection_handling"],
    },
    "ananya": {
        "product": "voice",
        "name": "Ananya",
        "emoji": "📅",
        "title": "Appointment Booker",
        "duties": "Har niche ke end-customers ke liye appointment, site-visit ya demo slot book karna — calendar + reminders",
        "schedule": "On-demand (booking campaigns / callbacks)",
        "skills": ["booking", "scheduling", "reminders"],
    },
    "riya": {
        "product": "voice",
        "name": "Riya",
        "emoji": "🛎️",
        "title": "AI Receptionist",
        "duties": "Inbound customer calls — greeting, department route, message lena, appointment book karna (sales pitch nahi)",
        "schedule": "On-demand (inbound / mini-site widget)",
        "skills": ["reception", "greeting", "routing"],
    },
    # Marketing agents (Dev, Rohan, Isha, etc.)
    "dev": {
        "product": "marketing",
        "name": "Dev",
        "emoji": "📚",
        "title": "Data Analyst",
        "duties": "Client business profile + niche knowledge KB me seed karna, RAG grounding maintain karna",
        "schedule": "Har naye client pe auto",
        "skills": ["data_analysis", "rag", "knowledge_base"],
    },
    "rohan": {
        "product": "marketing",
        "name": "Rohan",
        "emoji": "🎯",
        "title": "Leads Manager",
        "duties": "Outreach plan banana, lead qualification criteria set karna, campaigns ke liye targeting",
        "schedule": "On-demand (campaigns)",
        "skills": ["lead_generation", "targeting", "outreach"],
    },
    "arjun": {
        "product": "voice",
        "name": "Arjun",
        "emoji": "🧪",
        "title": "QA Engineer",
        "duties": "Agent performance QA, call quality checks, script validation",
        "schedule": "Daily scheduled + on-demand",
        "skills": ["quality_assurance", "validation", "testing"],
    },
    "meera": {
        "product": "voice",
        "name": "Meera",
        "emoji": "🎓",
        "title": "Trainer",
        "duties": "Voice agent training, transcript analysis, model improvement",
        "schedule": "Daily scheduled",
        "skills": ["training", "analysis", "improvement"],
    },
    "kavya": {
        "product": "platform",
        "name": "Kavya",
        "emoji": "⚙️",
        "title": "Ops Engineer",
        "duties": "System health monitoring, scheduler watchdog, automation flags",
        "schedule": "Hourly scheduled",
        "skills": ["operations", "monitoring", "automation"],
    },
    "isha": {
        "product": "marketing",
        "name": "Isha",
        "emoji": "📝",
        "title": "Content Creator",
        "duties": "Social media content, posts, captions, hashtags generation",
        "schedule": "On-demand (content campaigns)",
        "skills": ["content_creation", "social_media", "copywriting"],
    },
    # Additional agents to reach 31
    "tara": {
        "product": "marketing",
        "name": "Tara",
        "emoji": "📧",
        "title": "Email Specialist",
        "duties": "Email outreach, templates, tracking, deliverability",
        "schedule": "Hourly scheduled",
        "skills": ["email", "outreach", "deliverability"],
    },
    "neha": {
        "product": "marketing",
        "name": "Neha",
        "emoji": "📊",
        "title": "Analytics Lead",
        "duties": "Performance analytics, reporting, insights generation",
        "schedule": "Daily scheduled",
        "skills": ["analytics", "reporting", "insights"],
    },
    "priya": {
        "product": "voice",
        "name": "Priya",
        "emoji": "🎭",
        "title": "Voice Script Writer",
        "duties": "Script writing, objection handling templates, dialogue design",
        "schedule": "On-demand",
        "skills": ["scriptwriting", "dialogue", "templates"],
    },
    "vikram": {
        "product": "platform",
        "name": "Vikram",
        "emoji": "🔧",
        "title": "DevOps Engineer",
        "duties": "Infrastructure, deployments, monitoring, incident response",
        "schedule": "On-call",
        "skills": ["devops", "infrastructure", "monitoring"],
    },
    "kiran": {
        "product": "marketing",
        "name": "Kiran",
        "emoji": "📈",
        "title": "Growth Marketer",
        "duties": "Growth strategies, A/B testing, conversion optimization",
        "schedule": "Daily scheduled",
        "skills": ["growth", "ab_testing", "optimization"],
    },
    "zara": {
        "product": "marketing",
        "name": "Zara",
        "emoji": "🌐",
        "title": "Social Media Manager",
        "duties": "Social media management, posting, engagement tracking",
        "schedule": "Daily scheduled",
        "skills": ["social_media", "posting", "engagement"],
    },
    "kabir": {
        "product": "platform",
        "name": "Kabir",
        "emoji": "🗄️",
        "title": "DBA Engineer",
        "duties": "Database reliability, queries, indices, connections",
        "schedule": "Daily scheduled 10:00 IST",
        "skills": ["database", "queries", "optimization"],
    },
    "aryan": {
        "product": "platform",
        "name": "Aryan",
        "emoji": "📦",
        "title": "Dependency Engineer",
        "duties": "Dependency/supply-chain CVE audit, proposal-only",
        "schedule": "Weekly Sun 04:30",
        "skills": ["dependencies", "security", "auditing"],
    },
    "diya": {
        "product": "platform",
        "name": "Diya",
        "emoji": "🔍",
        "title": "Data Integrity Engineer",
        "duties": "Lead/CRM data integrity, report-only",
        "schedule": "Daily 10:30 IST",
        "skills": ["data_integrity", "validation", "reporting"],
    },
    "nikhil": {
        "product": "platform",
        "name": "Nikhil",
        "emoji": "💰",
        "title": "Revenue Ops",
        "duties": "Revenue tracking, billing, UPI confirmations",
        "schedule": "Hourly scheduled",
        "skills": ["revenue", "billing", "analytics"],
    },
    "arnav": {
        "product": "platform",
        "name": "Arnav",
        "emoji": "🔒",
        "title": "Security Engineer",
        "duties": "Security posture, compliance, audits",
        "schedule": "Daily scheduled",
        "skills": ["security", "compliance", "auditing"],
    },
    "hermes": {
        "product": "platform",
        "name": "Hermes",
        "emoji": "✉️",
        "title": "Communication Bot",
        "duties": "Telegram/WhatsApp notifications, alerts, deliverables",
        "schedule": "On-demand",
        "skills": ["messaging", "notifications", "deliverables"],
    },
    "arya": {
        "product": "platform",
        "name": "Arya",
        "emoji": "🔌",
        "title": "MCP Engineer",
        "duties": "MCP server health, tool routing, agent cards",
        "schedule": "Hourly scheduled :40",
        "skills": ["mcp", "routing", "health"],
    },
    "raju": {
        "product": "marketing",
        "name": "Raju",
        "emoji": "🎬",
        "title": "Video Producer",
        "duties": "Video ad creation, editing, publishing",
        "schedule": "Daily scheduled",
        "skills": ["video", "editing", "publishing"],
    },
    "simran": {
        "product": "marketing",
        "name": "Simran",
        "emoji": "📱",
        "title": "WhatsApp Specialist",
        "duties": "WhatsApp automation, templates, ban-safety checks",
        "schedule": "Hourly scheduled",
        "skills": ["whatsapp", "automation", "safety"],
    },
    "aditya": {
        "product": "platform",
        "name": "Aditya",
        "emoji": "🤖",
        "title": "Agent Runtime Engineer",
        "duties": "Agent runtime health, coordination, task queue",
        "schedule": "Hourly scheduled",
        "skills": ["runtime", "coordination", "queue"],
    },
    "pooja": {
        "product": "marketing",
        "name": "Pooja",
        "emoji": "📋",
        "title": "Campaign Manager",
        "duties": "Campaign planning, execution, tracking",
        "schedule": "Daily scheduled",
        "skills": ["campaigns", "planning", "tracking"],
    },
    "deepika": {
        "product": "marketing",
        "name": "Deepika",
        "emoji": "🔎",
        "title": "SEO Specialist",
        "duties": "SEO analysis, keyword research, rank tracking",
        "schedule": "Daily scheduled",
        "skills": ["seo", "keywords", "analytics"],
    },
    "aman": {
        "product": "platform",
        "name": "Aman",
        "emoji": "🛡️",
        "title": "Compliance Officer",
        "duties": "TRAI/DLP compliance, consent tracking, DLT management",
        "schedule": "Hourly scheduled",
        "skills": ["compliance", "regulatory", "tracking"],
    },
    "sonia": {
        "product": "marketing",
        "name": "Sonia",
        "emoji": "💬",
        "title": "Reply Agent",
        "duties": "Inquiry reply handling, triage, escalation",
        "schedule": "Hourly scheduled",
        "skills": ["reply", "triage", "escalation"],
    },
    "rajesh": {
        "product": "platform",
        "name": "Rajesh",
        "emoji": "📊",
        "title": "Reporting Lead",
        "duties": "Executive reports, dashboards, KPI tracking",
        "schedule": "Daily scheduled",
        "skills": ["reporting", "dashboards", "kpis"],
    },
}


class AgentManager:
    """Manage 31 agent bots with enterprise profiles."""
    
    def __init__(self):
        self.agents: dict[str, AgentProfile] = {}
        self._initialize_agents()
        self._load_memory()
    
    def _initialize_agents(self):
        """Initialize all 31 agent profiles."""
        for agent_id, profile_data in AGENT_PROFILES.items():
            agent = AgentProfile(
                agent_id=agent_id,
                name=profile_data["name"],
                role=profile_data["title"],
                product=profile_data["product"],
                emoji=profile_data["emoji"],
                duties=profile_data["duties"],
                schedule=profile_data["schedule"],
                skills=profile_data.get("skills", []),
            )
            self.agents[agent_id] = agent
    
    def _load_memory(self):
        """Load agent memory from disk."""
        memory_path = "data/agent_memory.json"
        if os.path.exists(memory_path):
            try:
                with open(memory_path, "r") as f:
                    memory = json.load(f)
                for agent_id, data in memory.items():
                    if agent_id in self.agents:
                        agent = self.agents[agent_id]
                        agent.tasks_completed_today = data.get("tasks_completed_today", 0)
                        agent.tasks_completed_total = data.get("tasks_completed_total", 0)
                        agent.last_active = data.get("last_active")
            except Exception as e:
                print(f"[agent_manager] Failed to load memory: {e}")
    
    def _save_memory(self):
        """Save agent memory to disk."""
        memory_path = "data/agent_memory.json"
        try:
            memory = {}
            for agent_id, agent in self.agents.items():
                memory[agent_id] = {
                    "tasks_completed_today": agent.tasks_completed_today,
                    "tasks_completed_total": agent.tasks_completed_total,
                    "last_active": agent.last_active,
                }
            os.makedirs(os.path.dirname(memory_path), exist_ok=True)
            with open(memory_path, "w") as f:
                json.dump(memory, f, indent=2)
        except Exception as e:
            print(f"[agent_manager] Failed to save memory: {e}")
    
    def get_agent(self, agent_id: str) -> Optional[AgentProfile]:
        """Get agent by ID."""
        return self.agents.get(agent_id)
    
    def list_agents(self, product: Optional[str] = None) -> list[dict[str, Any]]:
        """List all agents, optionally filtered by product."""
        result = []
        for agent in self.agents.values():
            if product and agent.product != product:
                continue
            result.append(agent.to_dict())
        return result
    
    def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        """Get detailed stats for an agent."""
        agent = self.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}
        
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "role": agent.role,
            "product": agent.product,
            "status": agent.status,
            "skills": agent.skills,
            "tasks_completed_today": agent.tasks_completed_today,
            "tasks_completed_total": agent.tasks_completed_total,
            "last_active": agent.last_active,
        }
    
    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        """Activate an agent (set status to 'working')."""
        agent = self.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}
        
        agent.status = "working"
        agent.last_active = datetime.now(_IST).isoformat()
        self._save_memory()
        
        return {"success": True, "agent_id": agent_id, "status": agent.status}
    
    def pause_agent(self, agent_id: str) -> dict[str, Any]:
        """Pause an agent (set status to 'idle')."""
        agent = self.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}
        
        agent.status = "idle"
        self._save_memory()
        
        return {"success": True, "agent_id": agent_id, "status": agent.status}
    
    def increment_task_count(self, agent_id: str) -> dict[str, Any]:
        """Increment task completed count for an agent."""
        agent = self.get_agent(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found"}
        
        agent.tasks_completed_today += 1
        agent.tasks_completed_total += 1
        agent.last_active = datetime.now(_IST).isoformat()
        self._save_memory()
        
        return {
            "success": True,
            "agent_id": agent_id,
            "tasks_today": agent.tasks_completed_today,
            "tasks_total": agent.tasks_completed_total,
        }
    
    def get_daily_summary(self) -> dict[str, Any]:
        """Get daily summary of all agent activity."""
        today = datetime.now(_IST).date()
        
        total_agents = len(self.agents)
        active_agents = len([a for a in self.agents.values() if a.status == "working"])
        total_tasks_today = sum(a.tasks_completed_today for a in self.agents.values())
        total_tasks_all = sum(a.tasks_completed_total for a in self.agents.values())
        
        # Per-product breakdown
        marketing_agents = len([a for a in self.agents.values() if a.product == "marketing"])
        voice_agents = len([a for a in self.agents.values() if a.product == "voice"])
        platform_agents = len([a for a in self.agents.values() if a.product == "platform"])
        
        return {
            "date": today.isoformat(),
            "total_agents": total_agents,
            "active_agents": active_agents,
            "total_tasks_today": total_tasks_today,
            "total_tasks_all": total_tasks_all,
            "breakdown": {
                "marketing": {
                    "agents": marketing_agents,
                    "tasks_today": sum(a.tasks_completed_today for a in self.agents.values() if a.product == "marketing"),
                },
                "voice": {
                    "agents": voice_agents,
                    "tasks_today": sum(a.tasks_completed_today for a in self.agents.values() if a.product == "voice"),
                },
                "platform": {
                    "agents": platform_agents,
                    "tasks_today": sum(a.tasks_completed_today for a in self.agents.values() if a.product == "platform"),
                },
            },
        }


# Module-level singleton
_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """Get or create singleton AgentManager."""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager


def list_agents(product: Optional[str] = None) -> list[dict[str, Any]]:
    """Convenience function to list agents."""
    return get_agent_manager().list_agents(product)


def get_agent_stats(agent_id: str) -> dict[str, Any]:
    """Convenience function to get agent stats."""
    return get_agent_manager().get_agent_stats(agent_id)


def daily_summary() -> dict[str, Any]:
    """Convenience function to get daily summary."""
    return get_agent_manager().get_daily_summary()
