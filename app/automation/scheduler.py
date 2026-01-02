"""
Call Scheduler
Handles intelligent call scheduling and timing
"""
import asyncio
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
import pytz

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DayOfWeek(Enum):
    """Days of the week"""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


@dataclass
class ScheduleConfig:
    """Schedule configuration"""
    working_days: List[DayOfWeek]
    start_time: time
    end_time: time
    timezone: str
    
    # Call pacing
    calls_per_hour: int
    max_concurrent: int
    
    # Breaks
    lunch_start: Optional[time] = None
    lunch_end: Optional[time] = None


class CallScheduler:
    """
    Intelligent Call Scheduler
    
    Handles:
    - Working hours enforcement
    - Call pacing
    - Time zone management
    - Optimal call timing
    - Holiday handling
    """
    
    # Best call times by industry (based on research)
    OPTIMAL_CALL_TIMES = {
        "real_estate": {
            "best_hours": [10, 11, 14, 15, 16],
            "best_days": [DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY]
        },
        "solar": {
            "best_hours": [10, 11, 14, 15],
            "best_days": [DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY]
        },
        "logistics": {
            "best_hours": [9, 10, 11, 14, 15],
            "best_days": [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY]
        },
        "digital_marketing": {
            "best_hours": [10, 11, 14, 15, 16],
            "best_days": [DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY]
        },
        "manufacturing": {
            "best_hours": [10, 11, 14, 15],
            "best_days": [DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY]
        },
        "insurance": {
            "best_hours": [10, 11, 14, 15, 16, 17],
            "best_days": [DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]
        }
    }
    
    # Indian public holidays (major ones)
    INDIAN_HOLIDAYS_2024 = [
        datetime(2024, 1, 26),   # Republic Day
        datetime(2024, 3, 25),   # Holi
        datetime(2024, 4, 14),   # Ambedkar Jayanti
        datetime(2024, 8, 15),   # Independence Day
        datetime(2024, 10, 2),   # Gandhi Jayanti
        datetime(2024, 10, 12),  # Dussehra
        datetime(2024, 11, 1),   # Diwali
        datetime(2024, 12, 25),  # Christmas
    ]
    
    def __init__(self, config: Optional[ScheduleConfig] = None):
        if config:
            self.config = config
        else:
            # Default configuration
            self.config = ScheduleConfig(
                working_days=[
                    DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
                    DayOfWeek.THURSDAY, DayOfWeek.FRIDAY, DayOfWeek.SATURDAY
                ],
                start_time=time(9, 0),
                end_time=time(18, 0),
                timezone=settings.timezone,
                calls_per_hour=20,
                max_concurrent=settings.max_concurrent_calls,
                lunch_start=time(13, 0),
                lunch_end=time(14, 0)
            )
        
        self.tz = pytz.timezone(self.config.timezone)
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info(f"📅 Call Scheduler initialized ({self.config.timezone})")
    
    def is_working_time(self, dt: Optional[datetime] = None) -> bool:
        """Check if given time is within working hours"""
        if dt is None:
            dt = datetime.now(self.tz)
        elif dt.tzinfo is None:
            dt = self.tz.localize(dt)
        
        # Check day of week
        if DayOfWeek(dt.weekday()) not in self.config.working_days:
            return False
        
        # Check holiday
        if self._is_holiday(dt):
            return False
        
        # Check time
        current_time = dt.time()
        
        if current_time < self.config.start_time or current_time > self.config.end_time:
            return False
        
        # Check lunch break
        if self.config.lunch_start and self.config.lunch_end:
            if self.config.lunch_start <= current_time <= self.config.lunch_end:
                return False
        
        return True
    
    def _is_holiday(self, dt: datetime) -> bool:
        """Check if date is a holiday"""
        date_only = dt.date()
        for holiday in self.INDIAN_HOLIDAYS_2024:
            if holiday.date() == date_only:
                return True
        return False
    
    def get_next_working_time(self, from_time: Optional[datetime] = None) -> datetime:
        """Get the next available working time"""
        if from_time is None:
            from_time = datetime.now(self.tz)
        elif from_time.tzinfo is None:
            from_time = self.tz.localize(from_time)
        
        # If current time is within working hours, return it
        if self.is_working_time(from_time):
            return from_time
        
        # Otherwise, find next working time
        check_time = from_time
        
        for _ in range(14 * 24):  # Check up to 2 weeks
            check_time += timedelta(hours=1)
            
            if self.is_working_time(check_time):
                # Align to start of hour
                return check_time.replace(minute=0, second=0, microsecond=0)
        
        # Fallback: next day start time
        next_day = from_time + timedelta(days=1)
        return next_day.replace(
            hour=self.config.start_time.hour,
            minute=self.config.start_time.minute,
            second=0,
            microsecond=0
        )
    
    def get_optimal_call_times(
        self,
        niche: str,
        count: int,
        start_from: Optional[datetime] = None
    ) -> List[datetime]:
        """
        Get optimal call times for a niche
        
        Returns list of datetime objects for best call times
        """
        if start_from is None:
            start_from = datetime.now(self.tz)
        elif start_from.tzinfo is None:
            start_from = self.tz.localize(start_from)
        
        optimal_config = self.OPTIMAL_CALL_TIMES.get(niche, {
            "best_hours": [10, 11, 14, 15, 16],
            "best_days": [DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY]
        })
        
        best_hours = optimal_config["best_hours"]
        best_days = optimal_config["best_days"]
        
        times = []
        check_date = start_from.date()
        calls_per_slot = max(1, count // (len(best_hours) * 5))  # Spread across 5 days
        
        while len(times) < count:
            check_dt = self.tz.localize(datetime.combine(check_date, time(9, 0)))
            
            # Check if it's a good day
            day_of_week = DayOfWeek(check_dt.weekday())
            
            if day_of_week in self.config.working_days and not self._is_holiday(check_dt):
                # Prioritize best days
                priority = 1.0 if day_of_week in best_days else 0.5
                
                for hour in best_hours:
                    if len(times) >= count:
                        break
                    
                    slot_time = check_dt.replace(hour=hour)
                    
                    if self.is_working_time(slot_time):
                        # Add multiple calls to this slot based on pacing
                        for i in range(min(calls_per_slot, self.config.calls_per_hour)):
                            if len(times) >= count:
                                break
                            
                            call_time = slot_time + timedelta(minutes=i * 3)
                            times.append(call_time)
            
            check_date += timedelta(days=1)
            
            # Safety: don't look more than 30 days ahead
            if (check_date - start_from.date()).days > 30:
                break
        
        return times
    
    def calculate_call_distribution(
        self,
        total_calls: int,
        days: int,
        niche: str
    ) -> Dict[str, List[int]]:
        """
        Calculate how calls should be distributed across days/hours
        
        Returns:
            Dict with date strings as keys and list of call counts per hour
        """
        distribution = {}
        
        start_date = datetime.now(self.tz).date()
        daily_limit = min(
            total_calls // days,
            self.config.calls_per_hour * 8  # Max 8 hours of calling
        )
        
        for day_offset in range(days):
            check_date = start_date + timedelta(days=day_offset)
            check_dt = self.tz.localize(datetime.combine(check_date, time(9, 0)))
            
            if DayOfWeek(check_dt.weekday()) not in self.config.working_days:
                continue
            
            if self._is_holiday(check_dt):
                continue
            
            date_str = check_date.isoformat()
            distribution[date_str] = []
            
            calls_remaining = daily_limit
            
            for hour in range(self.config.start_time.hour, self.config.end_time.hour):
                if calls_remaining <= 0:
                    break
                
                hour_time = check_dt.replace(hour=hour)
                
                if not self.is_working_time(hour_time):
                    distribution[date_str].append(0)
                    continue
                
                calls_this_hour = min(calls_remaining, self.config.calls_per_hour)
                distribution[date_str].append(calls_this_hour)
                calls_remaining -= calls_this_hour
        
        return distribution
    
    async def schedule_task(
        self,
        task_id: str,
        scheduled_time: datetime,
        callback: Callable,
        *args,
        **kwargs
    ):
        """Schedule a task to run at a specific time"""
        if scheduled_time.tzinfo is None:
            scheduled_time = self.tz.localize(scheduled_time)
        
        now = datetime.now(self.tz)
        delay = (scheduled_time - now).total_seconds()
        
        if delay < 0:
            logger.warning(f"Task {task_id} scheduled for past time, running immediately")
            delay = 0
        
        async def run_scheduled():
            await asyncio.sleep(delay)
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Scheduled task {task_id} failed: {e}")
            finally:
                if task_id in self.scheduled_tasks:
                    del self.scheduled_tasks[task_id]
        
        task = asyncio.create_task(run_scheduled())
        self.scheduled_tasks[task_id] = task
        
        logger.debug(f"Task {task_id} scheduled for {scheduled_time}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task"""
        task = self.scheduled_tasks.get(task_id)
        if task:
            task.cancel()
            del self.scheduled_tasks[task_id]
            return True
        return False
    
    def get_time_until_next_working_hour(self) -> timedelta:
        """Get time until next working hour starts"""
        now = datetime.now(self.tz)
        next_time = self.get_next_working_time(now)
        return next_time - now


class LeadScorer:
    """
    Lead scoring based on various factors
    """
    
    SCORING_WEIGHTS = {
        "is_decision_maker": 25,
        "has_budget": 20,
        "has_timeline": 15,
        "has_pain_points": 15,
        "interest_level_high": 15,
        "verified_business": 10,
        "appointment_scheduled": 30,
        "callback_requested": 10
    }
    
    def calculate_score(self, lead_data: Dict[str, Any]) -> int:
        """Calculate lead score based on qualification data"""
        score = 0
        
        if lead_data.get("is_decision_maker"):
            score += self.SCORING_WEIGHTS["is_decision_maker"]
        
        if lead_data.get("budget"):
            score += self.SCORING_WEIGHTS["has_budget"]
        
        if lead_data.get("timeline"):
            score += self.SCORING_WEIGHTS["has_timeline"]
        
        if lead_data.get("pain_points"):
            score += self.SCORING_WEIGHTS["has_pain_points"]
        
        if lead_data.get("interest_level") == "high":
            score += self.SCORING_WEIGHTS["interest_level_high"]
        
        if lead_data.get("verified"):
            score += self.SCORING_WEIGHTS["verified_business"]
        
        if lead_data.get("appointment_scheduled"):
            score += self.SCORING_WEIGHTS["appointment_scheduled"]
        
        if lead_data.get("callback_requested"):
            score += self.SCORING_WEIGHTS["callback_requested"]
        
        return min(100, score)


class AutoFollowUp:
    """
    Automated follow-up system
    """
    
    FOLLOW_UP_TEMPLATES = {
        "no_answer": {
            "delay_hours": 24,
            "max_attempts": 3,
            "message": "We tried reaching you earlier. Would you like to schedule a call?"
        },
        "callback_requested": {
            "delay_hours": 0,  # At requested time
            "max_attempts": 2,
            "message": "This is your scheduled callback from {client_name}."
        },
        "interested": {
            "delay_hours": 48,
            "max_attempts": 2,
            "message": "Following up on our conversation about {service}."
        },
        "appointment_reminder": {
            "delay_hours": -2,  # 2 hours before appointment
            "max_attempts": 1,
            "message": "Reminder: Your meeting with {client_name} is in 2 hours."
        }
    }
    
    def __init__(self, scheduler: CallScheduler):
        self.scheduler = scheduler
        self.pending_followups: Dict[str, Dict[str, Any]] = {}
    
    async def schedule_followup(
        self,
        lead_id: str,
        followup_type: str,
        client_name: str,
        service: str,
        base_time: Optional[datetime] = None
    ):
        """Schedule a follow-up based on type"""
        template = self.FOLLOW_UP_TEMPLATES.get(followup_type)
        if not template:
            return
        
        if base_time is None:
            base_time = datetime.now()
        
        followup_time = base_time + timedelta(hours=template["delay_hours"])
        
        # Ensure it's during working hours
        followup_time = self.scheduler.get_next_working_time(followup_time)
        
        self.pending_followups[lead_id] = {
            "type": followup_type,
            "scheduled_time": followup_time,
            "attempts": 0,
            "max_attempts": template["max_attempts"],
            "message": template["message"].format(
                client_name=client_name,
                service=service
            )
        }
        
        logger.info(f"Follow-up scheduled for lead {lead_id} at {followup_time}")
