"""
Auto Trainer - Nightly Batch Training System
Automatically trains and improves ML models based on collected data

Features:
- Train intent classifier on real conversation data
- Train lead scoring model on conversion outcomes
- Optimize prompts based on successful patterns
- Generate new response variants for A/B testing
- Manage model versions and rollback
"""
import json
import asyncio
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from app.utils.logger import setup_logger
from app.ml.data_pipeline import ConversationDataPipeline, ConversationRecord, ConversationOutcome
from app.ml.feedback_loop import FeedbackLoop, CallOutcome

logger = setup_logger(__name__)


class ModelType(Enum):
    """Types of models we train"""
    INTENT_CLASSIFIER = "intent_classifier"
    LEAD_SCORER = "lead_scorer"
    RESPONSE_RANKER = "response_ranker"
    SENTIMENT_ANALYZER = "sentiment_analyzer"


class TrainingStatus(Enum):
    """Status of a training job"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TrainingMetrics:
    """Metrics from a training run"""
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    
    # For regression models (lead scoring)
    mse: float = 0.0
    mae: float = 0.0
    r2_score: float = 0.0
    
    # Training info
    samples_used: int = 0
    training_time_seconds: float = 0.0


@dataclass
class ModelVersion:
    """Tracks a specific version of a model"""
    model_type: ModelType
    version: str
    created_at: datetime = field(default_factory=datetime.now)
    
    # Training details
    training_data_from: datetime = None
    training_data_to: datetime = None
    samples_count: int = 0
    
    # Performance
    metrics: TrainingMetrics = field(default_factory=TrainingMetrics)
    
    # Status
    is_active: bool = False
    file_path: str = ""


@dataclass
class TrainingJob:
    """A training job to be executed"""
    job_id: str
    model_type: ModelType
    status: TrainingStatus = TrainingStatus.PENDING
    
    # Schedule
    scheduled_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    metrics: Optional[TrainingMetrics] = None
    error_message: Optional[str] = None
    new_version: Optional[str] = None


class AutoTrainer:
    """
    Automatic model training system
    
    Runs nightly to:
    1. Collect new conversation data
    2. Train/update ML models
    3. Evaluate performance
    4. Deploy improved models
    5. Generate optimized prompts
    """
    
    def __init__(
        self,
        models_dir: str = "models",
        data_pipeline: ConversationDataPipeline = None,
        feedback_loop: FeedbackLoop = None
    ):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.data_pipeline = data_pipeline or ConversationDataPipeline()
        self.feedback_loop = feedback_loop or FeedbackLoop()
        
        # Model versions registry
        self.model_versions: Dict[ModelType, List[ModelVersion]] = {
            model_type: [] for model_type in ModelType
        }
        
        # Active models (loaded in memory)
        self.active_models: Dict[ModelType, Any] = {}
        
        # Pending training jobs
        self.job_queue: List[TrainingJob] = []
        
        # Training history
        self.training_history: List[TrainingJob] = []
        
        # Load existing models
        self._load_model_registry()
        
        logger.info("🎓 Auto Trainer initialized")
    
    def _load_model_registry(self):
        """Load model registry from disk"""
        registry_file = self.models_dir / "registry.json"
        if registry_file.exists():
            try:
                with open(registry_file, "r") as f:
                    data = json.load(f)
                logger.info(f"📂 Loaded model registry")
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}")
    
    def _save_model_registry(self):
        """Save model registry to disk"""
        registry_file = self.models_dir / "registry.json"
        
        data = {
            model_type.value: [
                {
                    "version": v.version,
                    "created_at": v.created_at.isoformat(),
                    "is_active": v.is_active,
                    "file_path": v.file_path,
                    "samples_count": v.samples_count
                }
                for v in versions
            ]
            for model_type, versions in self.model_versions.items()
        }
        
        with open(registry_file, "w") as f:
            json.dump(data, f, indent=2)
    
    async def run_nightly_training(self):
        """
        Main nightly training routine
        Called by scheduler at configured time (e.g., 2 AM)
        """
        logger.info("🌙 Starting nightly training routine...")
        
        training_start = datetime.now()
        results = {}
        
        try:
            # 1. Train intent classifier
            logger.info("📚 Training intent classifier...")
            intent_result = await self.train_intent_classifier()
            results["intent_classifier"] = intent_result
            
            # 2. Train lead scorer
            logger.info("📊 Training lead scorer...")
            scorer_result = await self.train_lead_scorer()
            results["lead_scorer"] = scorer_result
            
            # 3. Optimize prompts based on feedback
            logger.info("✨ Optimizing prompts...")
            prompt_result = await self.optimize_prompts()
            results["prompt_optimization"] = prompt_result
            
            # 4. Generate A/B test variants
            logger.info("🧪 Generating A/B test variants...")
            ab_result = await self.generate_ab_variants()
            results["ab_variants"] = ab_result
            
            training_duration = (datetime.now() - training_start).total_seconds()
            
            logger.info(f"✅ Nightly training completed in {training_duration:.1f}s")
            
            return {
                "status": "success",
                "duration_seconds": training_duration,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"❌ Nightly training failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "results": results
            }
    
    async def train_intent_classifier(self) -> Dict:
        """
        Train/update the intent classification model
        
        Uses conversation data to learn:
        - Which phrases map to which intents
        - Industry-specific language patterns
        - Hindi/English/Hinglish variations
        """
        
        job = TrainingJob(
            job_id=f"intent_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            model_type=ModelType.INTENT_CLASSIFIER
        )
        job.status = TrainingStatus.RUNNING
        job.started_at = datetime.now()
        
        try:
            # Get training data
            records = self.data_pipeline.get_training_data(
                min_turns=3,
                limit=5000
            )
            
            if len(records) < 100:
                logger.warning("Insufficient data for intent training (< 100 samples)")
                return {"status": "skipped", "reason": "insufficient_data"}
            
            # Prepare training data
            X_texts = []
            y_intents = []
            
            for record in records:
                for turn in record.turns:
                    if turn.role == "user" and turn.intent:
                        X_texts.append(turn.content)
                        y_intents.append(turn.intent)
            
            if len(X_texts) < 50:
                return {"status": "skipped", "reason": "insufficient_labeled_data"}
            
            # Train model using scikit-learn
            metrics = await self._train_sklearn_classifier(
                X_texts, y_intents, "intent_classifier"
            )
            
            job.status = TrainingStatus.COMPLETED
            job.completed_at = datetime.now()
            job.metrics = metrics
            
            # Create new version
            version = f"v{len(self.model_versions[ModelType.INTENT_CLASSIFIER]) + 1}"
            model_version = ModelVersion(
                model_type=ModelType.INTENT_CLASSIFIER,
                version=version,
                samples_count=len(X_texts),
                metrics=metrics,
                is_active=True,
                file_path=str(self.models_dir / f"intent_classifier_{version}.pkl")
            )
            
            # Deactivate previous versions
            for v in self.model_versions[ModelType.INTENT_CLASSIFIER]:
                v.is_active = False
            
            self.model_versions[ModelType.INTENT_CLASSIFIER].append(model_version)
            self._save_model_registry()
            
            return {
                "status": "success",
                "version": version,
                "samples": len(X_texts),
                "accuracy": metrics.accuracy
            }
            
        except Exception as e:
            job.status = TrainingStatus.FAILED
            job.error_message = str(e)
            logger.error(f"Intent training failed: {e}")
            return {"status": "failed", "error": str(e)}
        
        finally:
            self.training_history.append(job)
    
    async def _train_sklearn_classifier(
        self,
        texts: List[str],
        labels: List[str],
        model_name: str
    ) -> TrainingMetrics:
        """Train a text classifier using scikit-learn"""
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.naive_bayes import MultinomialNB
            from sklearn.pipeline import Pipeline
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        except ImportError:
            logger.error("scikit-learn not installed")
            return TrainingMetrics()
        
        import time
        start_time = time.time()
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, random_state=42
        )
        
        # Create and train pipeline
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                max_features=5000,
                ngram_range=(1, 2),
                min_df=2
            )),
            ('clf', MultinomialNB())
        ])
        
        pipeline.fit(X_train, y_train)
        
        # Evaluate
        y_pred = pipeline.predict(X_test)
        
        metrics = TrainingMetrics(
            accuracy=accuracy_score(y_test, y_pred),
            precision=precision_score(y_test, y_pred, average='weighted', zero_division=0),
            recall=recall_score(y_test, y_pred, average='weighted', zero_division=0),
            f1_score=f1_score(y_test, y_pred, average='weighted', zero_division=0),
            samples_used=len(texts),
            training_time_seconds=time.time() - start_time
        )
        
        # Save model
        model_path = self.models_dir / f"{model_name}_latest.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(pipeline, f)
        
        logger.info(
            f"📈 {model_name} trained: "
            f"accuracy={metrics.accuracy:.3f}, "
            f"f1={metrics.f1_score:.3f}"
        )
        
        return metrics
    
    async def train_lead_scorer(self) -> Dict:
        """
        Train lead scoring model
        
        Predicts conversion probability based on:
        - Conversation features (length, engagement, questions)
        - Lead characteristics (industry, size, etc.)
        - Agent responses used
        """
        
        try:
            # Get training data with outcomes
            records = self.data_pipeline.get_training_data(limit=5000)
            
            if len(records) < 50:
                return {"status": "skipped", "reason": "insufficient_data"}
            
            # Prepare features and labels
            X_features = []
            y_scores = []
            
            successful_outcomes = {
                ConversationOutcome.APPOINTMENT_BOOKED,
                ConversationOutcome.CALLBACK_SCHEDULED,
                ConversationOutcome.INTERESTED
            }
            
            for record in records:
                # Extract features
                features = [
                    record.features.total_turns,
                    record.features.avg_user_response_length,
                    record.features.user_question_count,
                    record.features.user_objection_count,
                    record.features.positive_signals,
                    record.features.negative_signals,
                    1 if record.features.is_decision_maker else 0,
                    1 if record.features.has_budget else 0,
                    1 if record.features.has_timeline else 0,
                    1 if record.features.has_pain_point else 0
                ]
                
                X_features.append(features)
                
                # Binary outcome (1 = successful, 0 = not)
                y_scores.append(1 if record.outcome in successful_outcomes else 0)
            
            # Train model
            metrics = await self._train_sklearn_regressor(
                X_features, y_scores, "lead_scorer"
            )
            
            return {
                "status": "success",
                "samples": len(X_features),
                "accuracy": metrics.accuracy
            }
            
        except Exception as e:
            logger.error(f"Lead scorer training failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def _train_sklearn_regressor(
        self,
        features: List[List[float]],
        labels: List[float],
        model_name: str
    ) -> TrainingMetrics:
        """Train a regressor/classifier for lead scoring"""
        
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, mean_squared_error
        except ImportError:
            return TrainingMetrics()
        
        import time
        start_time = time.time()
        
        X_train, X_test, y_train, y_test = train_test_split(
            features, labels, test_size=0.2, random_state=42
        )
        
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        
        metrics = TrainingMetrics(
            accuracy=accuracy_score(y_test, y_pred),
            mse=mean_squared_error(y_test, y_pred),
            samples_used=len(features),
            training_time_seconds=time.time() - start_time
        )
        
        # Save model
        model_path = self.models_dir / f"{model_name}_latest.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        
        return metrics
    
    async def optimize_prompts(self) -> Dict:
        """
        Optimize LLM prompts based on successful conversations
        
        Analyzes top-performing responses to:
        - Identify effective phrases
        - Extract successful conversation patterns
        - Generate improved system prompts
        """
        
        try:
            # Get successful conversation patterns
            stats = self.feedback_loop.get_stats()
            
            # Find best performing patterns
            best_patterns = []
            for pattern_type, patterns in self.feedback_loop.patterns.items():
                top_patterns = sorted(
                    [p for p in patterns if p.times_used >= 5],
                    key=lambda p: p.success_rate,
                    reverse=True
                )[:3]
                best_patterns.extend(top_patterns)
            
            if not best_patterns:
                return {"status": "skipped", "reason": "no_patterns_with_enough_data"}
            
            # Generate optimized prompts using LLM
            optimized_prompts = await self._generate_optimized_prompts(best_patterns)
            
            # Save optimized prompts
            prompts_file = self.models_dir / "optimized_prompts.json"
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump(optimized_prompts, f, ensure_ascii=False, indent=2)
            
            return {
                "status": "success",
                "patterns_analyzed": len(best_patterns),
                "prompts_generated": len(optimized_prompts)
            }
            
        except Exception as e:
            logger.error(f"Prompt optimization failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def _generate_optimized_prompts(
        self,
        best_patterns: List
    ) -> Dict[str, str]:
        """Generate optimized prompts from best patterns"""
        
        # Group patterns by type
        patterns_by_type = {}
        for pattern in best_patterns:
            ptype = pattern.response_type
            if ptype not in patterns_by_type:
                patterns_by_type[ptype] = []
            patterns_by_type[ptype].append(pattern.response_text)
        
        optimized = {}
        
        for ptype, responses in patterns_by_type.items():
            # For now, just pick the best one
            # In production, could use LLM to synthesize
            if responses:
                optimized[ptype] = responses[0]
        
        return optimized
    
    async def generate_ab_variants(self) -> Dict:
        """
        Generate A/B test variants for responses
        
        Creates variations of successful responses to test
        different approaches and phrasings
        """
        
        try:
            # Get current best responses
            best_responses = {}
            
            for objection_type, handler in self.feedback_loop.objection_handlers.items():
                if handler.best_response:
                    best_responses[objection_type] = handler.best_response
            
            if not best_responses:
                return {"status": "skipped", "reason": "no_best_responses"}
            
            # Generate variants (in production, use LLM)
            variants = {}
            for objection_type, response in best_responses.items():
                variants[objection_type] = {
                    "control": response,
                    "variant_a": response.replace("aap", "aap log"),  # Simple variation
                    "variant_b": response  # Could use LLM to generate
                }
            
            # Save variants
            variants_file = self.models_dir / "ab_variants.json"
            with open(variants_file, "w", encoding="utf-8") as f:
                json.dump(variants, f, ensure_ascii=False, indent=2)
            
            return {
                "status": "success",
                "variants_generated": len(variants)
            }
            
        except Exception as e:
            logger.error(f"A/B variant generation failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    def load_model(self, model_type: ModelType) -> Optional[Any]:
        """Load a trained model for inference"""
        
        if model_type in self.active_models:
            return self.active_models[model_type]
        
        # Find active version
        versions = self.model_versions.get(model_type, [])
        active_version = next((v for v in versions if v.is_active), None)
        
        if not active_version:
            return None
        
        try:
            with open(active_version.file_path, 'rb') as f:
                model = pickle.load(f)
            
            self.active_models[model_type] = model
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model {model_type.value}: {e}")
            return None
    
    def predict_intent(self, text: str) -> Tuple[str, float]:
        """
        Predict intent using trained model
        
        Returns:
            (intent, confidence)
        """
        
        model = self.load_model(ModelType.INTENT_CLASSIFIER)
        
        if not model:
            return ("unknown", 0.0)
        
        try:
            intent = model.predict([text])[0]
            proba = model.predict_proba([text])[0]
            confidence = max(proba)
            
            return (intent, confidence)
            
        except Exception as e:
            logger.error(f"Intent prediction failed: {e}")
            return ("unknown", 0.0)
    
    def predict_lead_score(self, features: List[float]) -> float:
        """
        Predict lead conversion probability
        
        Returns:
            Score between 0 and 1
        """
        
        model = self.load_model(ModelType.LEAD_SCORER)
        
        if not model:
            return 0.5  # Default neutral score
        
        try:
            proba = model.predict_proba([features])[0]
            # Return probability of positive class
            return proba[1] if len(proba) > 1 else proba[0]
            
        except Exception as e:
            logger.error(f"Lead score prediction failed: {e}")
            return 0.5
    
    def get_training_stats(self) -> Dict:
        """Get training statistics"""
        
        return {
            "models": {
                model_type.value: {
                    "versions": len(versions),
                    "active": next(
                        (v.version for v in versions if v.is_active),
                        None
                    )
                }
                for model_type, versions in self.model_versions.items()
            },
            "jobs_completed": len([
                j for j in self.training_history
                if j.status == TrainingStatus.COMPLETED
            ]),
            "jobs_failed": len([
                j for j in self.training_history
                if j.status == TrainingStatus.FAILED
            ]),
            "last_training": self.training_history[-1].completed_at.isoformat()
            if self.training_history and self.training_history[-1].completed_at
            else None
        }


# Singleton instance
auto_trainer = AutoTrainer()
