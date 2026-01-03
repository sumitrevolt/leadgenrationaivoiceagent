"""
Vertex AI Training Pipeline
Production ML training for conversation models using Vertex AI
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
import uuid

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class TrainingJob:
    """Training job configuration"""
    job_id: str
    display_name: str
    model_type: str  # "intent_classifier", "sentiment", "objection_handler"
    status: str  # "pending", "running", "completed", "failed"
    created_at: str
    training_data_uri: str
    model_output_uri: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None
    error_message: Optional[str] = None


class VertexTrainingPipeline:
    """
    Vertex AI Training Pipeline for LeadGen AI
    Handles:
    - Intent classification model training
    - Sentiment analysis fine-tuning
    - Objection handling optimization
    - Model versioning and registry
    """
    
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.project_id = settings.google_cloud_project_id
        self.location = settings.google_cloud_location or "asia-south1"
        self.staging_bucket = f"gs://{self.project_id}-{settings.environment}-training-data"
        self.model_bucket = f"gs://{self.project_id}-{settings.environment}-ml-models"
        
        self._init_vertex()
    
    def _init_vertex(self):
        """Initialize Vertex AI SDK"""
        try:
            from google.cloud import aiplatform
            
            aiplatform.init(
                project=self.project_id,
                location=self.location,
                staging_bucket=self.staging_bucket,
            )
            self._aiplatform = aiplatform
            self._initialized = True
            logger.info(f"✅ Vertex AI Training initialized: {self.project_id}/{self.location}")
            
        except ImportError:
            logger.warning("google-cloud-aiplatform not installed")
            self._initialized = False
        except Exception as e:
            logger.warning(f"Vertex AI Training init failed: {e}")
            self._initialized = False
    
    async def prepare_training_data(
        self,
        data_type: str,
        conversations: List[Dict[str, Any]],
    ) -> str:
        """
        Prepare and upload training data to GCS
        
        Args:
            data_type: Type of training data ("intent", "sentiment", "objection")
            conversations: List of conversation records
            
        Returns:
            GCS URI of training data
        """
        if not self._initialized:
            raise RuntimeError("Vertex AI not initialized")
        
        from google.cloud import storage
        
        # Format data based on type
        if data_type == "intent":
            training_data = self._format_intent_data(conversations)
        elif data_type == "sentiment":
            training_data = self._format_sentiment_data(conversations)
        elif data_type == "objection":
            training_data = self._format_objection_data(conversations)
        else:
            raise ValueError(f"Unknown data type: {data_type}")
        
        # Upload to GCS
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"{self.tenant_id}/{data_type}/training_{timestamp}.jsonl"
        
        storage_client = storage.Client(project=self.project_id)
        bucket_name = self.staging_bucket.replace("gs://", "")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Write JSONL format
        jsonl_content = "\n".join(json.dumps(item) for item in training_data)
        await asyncio.to_thread(blob.upload_from_string, jsonl_content)
        
        uri = f"{self.staging_bucket}/{blob_name}"
        logger.info(f"📤 Training data uploaded: {uri} ({len(training_data)} examples)")
        
        return uri
    
    def _format_intent_data(self, conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format data for intent classification"""
        training_examples = []
        
        for conv in conversations:
            for turn in conv.get("turns", []):
                if turn.get("role") == "user" and turn.get("intent"):
                    training_examples.append({
                        "text": turn.get("content", ""),
                        "label": turn.get("intent"),
                        "industry": conv.get("industry", "general"),
                        "outcome": conv.get("outcome", "unknown"),
                    })
        
        return training_examples
    
    def _format_sentiment_data(self, conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format data for sentiment analysis"""
        training_examples = []
        
        for conv in conversations:
            for turn in conv.get("turns", []):
                if turn.get("role") == "user":
                    sentiment = turn.get("sentiment", "neutral")
                    training_examples.append({
                        "text": turn.get("content", ""),
                        "sentiment": sentiment,
                        "score": turn.get("sentiment_score", 0.0),
                    })
        
        return training_examples
    
    def _format_objection_data(self, conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format data for objection handling"""
        training_examples = []
        
        for conv in conversations:
            turns = conv.get("turns", [])
            for i, turn in enumerate(turns):
                if turn.get("intent") == "objection" and i + 1 < len(turns):
                    response = turns[i + 1]
                    if response.get("role") == "assistant":
                        # Check if objection was successfully handled
                        success = conv.get("outcome") in ["appointment_booked", "interested", "callback_scheduled"]
                        
                        training_examples.append({
                            "objection": turn.get("content", ""),
                            "response": response.get("content", ""),
                            "objection_type": turn.get("objection_type", "general"),
                            "industry": conv.get("industry", "general"),
                            "success": success,
                        })
        
        return training_examples
    
    async def train_intent_classifier(
        self,
        training_data_uri: str,
        display_name: Optional[str] = None,
    ) -> TrainingJob:
        """
        Train intent classification model using AutoML
        """
        if not self._initialized:
            raise RuntimeError("Vertex AI not initialized")
        
        job_id = f"intent-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        display_name = display_name or f"LeadGen Intent Classifier - {self.tenant_id}"
        
        logger.info(f"🚀 Starting intent classifier training: {job_id}")
        
        try:
            # Create dataset
            dataset = self._aiplatform.TextDataset.create(
                display_name=f"{display_name} Dataset",
                gcs_source=training_data_uri,
                import_schema_uri=self._aiplatform.schema.dataset.ioformat.text.single_label_classification,
            )
            
            # Start training
            job = self._aiplatform.AutoMLTextTrainingJob(
                display_name=display_name,
                prediction_type="classification",
            )
            
            model = await asyncio.to_thread(
                job.run,
                dataset=dataset,
                training_fraction_split=0.8,
                validation_fraction_split=0.1,
                test_fraction_split=0.1,
                model_display_name=f"{display_name} Model",
            )
            
            # Get metrics
            metrics = {}
            if hasattr(model, 'model_resource_name'):
                metrics["model_uri"] = model.model_resource_name
            
            return TrainingJob(
                job_id=job_id,
                display_name=display_name,
                model_type="intent_classifier",
                status="completed",
                created_at=datetime.now().isoformat(),
                training_data_uri=training_data_uri,
                model_output_uri=model.resource_name if model else None,
                metrics=metrics,
            )
            
        except Exception as e:
            logger.error(f"Intent classifier training failed: {e}")
            return TrainingJob(
                job_id=job_id,
                display_name=display_name,
                model_type="intent_classifier",
                status="failed",
                created_at=datetime.now().isoformat(),
                training_data_uri=training_data_uri,
                error_message=str(e),
            )
    
    async def train_custom_model(
        self,
        training_script_uri: str,
        training_data_uri: str,
        model_type: str,
        hyperparameters: Optional[Dict[str, Any]] = None,
        machine_type: str = "n1-standard-4",
        accelerator_type: Optional[str] = None,
        accelerator_count: int = 0,
    ) -> TrainingJob:
        """
        Train custom model using Vertex AI Custom Training
        For more complex models like objection handlers
        """
        if not self._initialized:
            raise RuntimeError("Vertex AI not initialized")
        
        job_id = f"custom-{model_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        display_name = f"LeadGen {model_type} - {self.tenant_id}"
        
        logger.info(f"🚀 Starting custom training job: {job_id}")
        
        try:
            # Define worker pool
            worker_pool_specs = [
                {
                    "machine_spec": {
                        "machine_type": machine_type,
                    },
                    "replica_count": 1,
                    "python_package_spec": {
                        "executor_image_uri": "us-docker.pkg.dev/vertex-ai/training/tf-cpu.2-12.py310:latest",
                        "package_uris": [training_script_uri],
                        "python_module": "trainer.task",
                        "args": [
                            f"--training_data={training_data_uri}",
                            f"--model_output={self.model_bucket}/{self.tenant_id}/{model_type}",
                            f"--hyperparameters={json.dumps(hyperparameters or {})}",
                        ],
                    },
                }
            ]
            
            # Add GPU if specified
            if accelerator_type and accelerator_count > 0:
                worker_pool_specs[0]["machine_spec"]["accelerator_type"] = accelerator_type
                worker_pool_specs[0]["machine_spec"]["accelerator_count"] = accelerator_count
            
            # Create custom job
            job = self._aiplatform.CustomJob(
                display_name=display_name,
                worker_pool_specs=worker_pool_specs,
                staging_bucket=self.staging_bucket,
            )
            
            # Run job
            await asyncio.to_thread(job.run, sync=True)
            
            return TrainingJob(
                job_id=job_id,
                display_name=display_name,
                model_type=model_type,
                status="completed",
                created_at=datetime.now().isoformat(),
                training_data_uri=training_data_uri,
                model_output_uri=f"{self.model_bucket}/{self.tenant_id}/{model_type}",
            )
            
        except Exception as e:
            logger.error(f"Custom training failed: {e}")
            return TrainingJob(
                job_id=job_id,
                display_name=display_name,
                model_type=model_type,
                status="failed",
                created_at=datetime.now().isoformat(),
                training_data_uri=training_data_uri,
                error_message=str(e),
            )
    
    async def register_model(
        self,
        model_artifact_uri: str,
        display_name: str,
        model_type: str,
        serving_container_image: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Register trained model in Vertex AI Model Registry
        """
        if not self._initialized:
            raise RuntimeError("Vertex AI not initialized")
        
        serving_container = serving_container_image or "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-0:latest"
        
        model = self._aiplatform.Model.upload(
            display_name=display_name,
            artifact_uri=model_artifact_uri,
            serving_container_image_uri=serving_container,
            labels=labels or {
                "tenant": self.tenant_id,
                "model_type": model_type,
                "version": datetime.now().strftime("%Y%m%d"),
            },
        )
        
        logger.info(f"✅ Model registered: {model.resource_name}")
        return model.resource_name
    
    async def deploy_model(
        self,
        model_resource_name: str,
        endpoint_display_name: str,
        machine_type: str = "n1-standard-2",
        min_replicas: int = 1,
        max_replicas: int = 5,
    ) -> str:
        """
        Deploy model to Vertex AI Endpoint for online prediction
        """
        if not self._initialized:
            raise RuntimeError("Vertex AI not initialized")
        
        # Get or create endpoint
        endpoints = self._aiplatform.Endpoint.list(
            filter=f'display_name="{endpoint_display_name}"',
            order_by="create_time desc",
        )
        
        if endpoints:
            endpoint = endpoints[0]
        else:
            endpoint = self._aiplatform.Endpoint.create(
                display_name=endpoint_display_name,
            )
        
        # Get model
        model = self._aiplatform.Model(model_resource_name)
        
        # Deploy
        await asyncio.to_thread(
            model.deploy,
            endpoint=endpoint,
            machine_type=machine_type,
            min_replica_count=min_replicas,
            max_replica_count=max_replicas,
            traffic_percentage=100,
        )
        
        logger.info(f"✅ Model deployed to: {endpoint.resource_name}")
        return endpoint.resource_name
    
    async def batch_predict(
        self,
        model_resource_name: str,
        input_uri: str,
        output_uri: str,
    ) -> str:
        """
        Run batch prediction job (50% cheaper than online)
        """
        if not self._initialized:
            raise RuntimeError("Vertex AI not initialized")
        
        model = self._aiplatform.Model(model_resource_name)
        
        batch_job = await asyncio.to_thread(
            model.batch_predict,
            job_display_name=f"batch-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            gcs_source=input_uri,
            gcs_destination_prefix=output_uri,
            instances_format="jsonl",
            predictions_format="jsonl",
            machine_type="n1-standard-4",
            starting_replica_count=1,
            max_replica_count=10,
            sync=False,
        )
        
        logger.info(f"📦 Batch prediction started: {batch_job.resource_name}")
        return batch_job.resource_name
    
    def list_models(
        self,
        model_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List registered models"""
        if not self._initialized:
            return []
        
        filter_str = f'labels.tenant="{self.tenant_id}"'
        if model_type:
            filter_str += f' AND labels.model_type="{model_type}"'
        
        models = self._aiplatform.Model.list(filter=filter_str)
        
        return [
            {
                "name": m.display_name,
                "resource_name": m.resource_name,
                "created": m.create_time.isoformat() if m.create_time else None,
                "labels": dict(m.labels) if m.labels else {},
            }
            for m in models
        ]
