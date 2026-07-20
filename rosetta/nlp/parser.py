"""NLP semantic parser using a fine-tuned T5-small encoder-decoder model.

Provides a dedicated text-to-JSON model (~60M params, ~20ms CPU inference)
for fast structured query plan generation. Falls back to the conversational
LLM (Ollama) if T5 is unavailable, not loaded, or produces invalid output.

The two-tier architecture:
  - NLPSemParser: fast, specialized → for structured data queries
  - Ollama (conversational LLM): slower, general → for chat, explanations,
    and as fallback when T5 fails

Usage:
    from nlp_model import NLPSemParser
    parser = NLPSemParser()           # loads t5-small
    plan = parser.parse("show employees with salary > 10000", schema_ddl)
"""

import json
import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class NLPSemParser:
    """T5-small based semantic parser for text-to-JSON-query-plan.

    Loads a HuggingFace transformers T5 model. If the model cannot be loaded
    (e.g., no network on first run, or missing torch), the parser gracefully
    degrades: parse() returns None, and the caller should fall back to Ollama.
    """

    _DEFAULT_MODEL = "t5-small"
    _PROMPT_TEMPLATE = (
        "translate text to JSON query plan: "
        "schema: {schema} | query: {query}"
    )

    def __init__(self, model_name: str | None = None):
        """Initialize the T5 semantic parser.

        Args:
            model_name: HuggingFace model ID. Defaults to "t5-small" (60M params).
                       Use "Salesforce/codet5-base" (220M) for identifier-aware,
                       or a path to a locally fine-tuned model.
        """
        self.model_name = model_name or self._DEFAULT_MODEL
        self.tokenizer = None
        self.model = None
        self._available = False
        self._load_error = None

        self._try_load()

    def _try_load(self):
        """Attempt to load the T5 model. Sets self._available on success."""
        try:
            from transformers import T5Tokenizer, T5ForConditionalGeneration

            logger.info("Loading T5 model: %s", self.model_name)
            self.tokenizer = T5Tokenizer.from_pretrained(
                self.model_name, legacy=False
            )
            self.model = T5ForConditionalGeneration.from_pretrained(
                self.model_name
            )
            self._available = True
            logger.info("T5 model loaded successfully (%s)", self.model_name)

        except ImportError:
            self._load_error = (
                "transformers and torch are required for the NLP model. "
                "Install with: pip install transformers torch"
            )
            logger.warning("T5 not available: %s", self._load_error)

        except Exception as e:
            self._load_error = str(e)
            logger.warning("Failed to load T5 model: %s", e)

    @property
    def available(self) -> bool:
        """Whether the T5 model is loaded and ready for inference."""
        return self._available

    @property
    def error(self) -> str | None:
        """Why the model isn't available, or None if ready."""
        return self._load_error

    def parse(self, user_query: str, schema_ddl: str) -> dict | None:
        """Convert a natural language query to a JSON query plan dict.

        Args:
            user_query: The natural language question.
            schema_ddl: Schema description text (DDL for SQL, field list for
                       MongoDB, node/relationship summary for Neo4j).

        Returns:
            Parsed query plan dict, or None if the model is unavailable
            or produces unparseable output.
        """
        if not self._available:
            logger.debug("T5 model not available, returning None for fallback")
            return None

        prompt = self._PROMPT_TEMPLATE.format(
            schema=schema_ddl, query=user_query
        )

        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                max_length=512,
                truncation=True,
            )
            outputs = self.model.generate(
                **inputs,
                max_length=256,
                num_beams=4,
                early_stopping=True,
            )
            json_text = self.tokenizer.decode(
                outputs[0], skip_special_tokens=True
            )

            # Clean and parse
            json_text = json_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()

            plan = json.loads(json_text)
            return plan

        except json.JSONDecodeError:
            logger.debug("T5 produced invalid JSON, returning None for fallback")
            return None

        except Exception as e:
            logger.warning("T5 inference error: %s", e)
            return None

    def is_fine_tunable(self) -> bool:
        """Whether the model supports fine-tuning (always True if loaded)."""
        return self._available and self.model is not None

    def train(
        self,
        train_pairs: list[tuple[str, str, str]],
        output_dir: str = "./t5_semparse_finetuned",
        epochs: int = 10,
        batch_size: int = 8,
        learning_rate: float = 5e-5,
    ):
        """Fine-tune the T5 model on (query, schema, plan) pairs.

        Args:
            train_pairs: List of (natural_language, schema_ddl, json_plan_string) tuples.
            output_dir: Where to save the fine-tuned model.
            epochs, batch_size, learning_rate: Training hyperparameters.
        """
        if not self._available:
            raise RuntimeError("T5 model is not loaded. Cannot train.")

        try:
            from transformers import (
                Seq2SeqTrainingArguments,
                Seq2SeqTrainer,
            )
            from datasets import Dataset
        except ImportError:
            raise ImportError(
                "datasets is required for training. Install with: pip install datasets"
            )

        # Build dataset
        inputs = []
        targets = []
        for nl, schema, plan_json in train_pairs:
            prompt = self._PROMPT_TEMPLATE.format(schema=schema, query=nl)
            inputs.append(prompt)
            targets.append(plan_json)

        def preprocess(examples):
            model_inputs = self.tokenizer(
                examples["input"],
                max_length=512,
                truncation=True,
                padding="max_length",
            )
            labels = self.tokenizer(
                examples["target"],
                max_length=256,
                truncation=True,
                padding="max_length",
            )
            model_inputs["labels"] = labels["input_ids"]
            return model_inputs

        dataset = Dataset.from_dict({"input": inputs, "target": targets})
        dataset = dataset.map(preprocess, batched=True)

        training_args = Seq2SeqTrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=batch_size,
            num_train_epochs=epochs,
            learning_rate=learning_rate,
            warmup_steps=100,
            weight_decay=0.01,
            logging_dir=f"{output_dir}/logs",
            save_strategy="epoch",
            save_total_limit=3,
            predict_with_generate=True,
        )

        trainer = Seq2SeqTrainer(
            model=self.model,
            args=training_args,
            train_dataset=dataset,
            tokenizer=self.tokenizer,
        )

        trainer.train()
        self.model.save_pretrained(output_dir)
        self.tokenizer.save_pretrained(output_dir)
        logger.info("Fine-tuned model saved to %s", output_dir)


# Singleton instance for the application
_default_parser: NLPSemParser | None = None


def get_parser(model_name: str | None = None) -> NLPSemParser:
    """Get or create the global NLPSemParser instance."""
    global _default_parser
    if _default_parser is None or model_name is not None:
        _default_parser = NLPSemParser(model_name)
    return _default_parser
