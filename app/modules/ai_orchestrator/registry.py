from typing import Callable, Dict


class AITaskRegistry:
    """
    Registry for AI Orchestrator Celery tasks.
    Enables Open/Closed Principle by allowing dynamic task dispatching without modifying the core service logic.
    """

    _tasks: Dict[str, Callable] = {}

    @classmethod
    def register(cls, task_type: str) -> Callable:
        """
        Decorator to register a Celery task.
        Must be placed ABOVE the @celery_app.task decorator to capture the task object.
        """

        def decorator(celery_task: Callable) -> Callable:
            if task_type in cls._tasks:
                raise ValueError(
                    f"Task '{task_type}' is already registered in AITaskRegistry."
                )

            cls._tasks[task_type] = celery_task

            return celery_task

        return decorator

    @classmethod
    def get_task(cls, task_type: str) -> Callable:
        """
        Retrieves the registered Celery task.
        """
        if task_type not in cls._tasks:
            raise ValueError(f"Unknown task type: '{task_type}'")
        return cls._tasks[task_type]
