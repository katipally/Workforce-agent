"""
Background scheduler for modular workflows (v2).

Runs active workflows based on their schedule_type and schedule_config.
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from config import Config
from core.database.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger(__name__)

# Global state for the scheduler thread
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop_event = threading.Event()


def start_workflow_scheduler(db_manager: DatabaseManager) -> None:
    """Start the background workflow scheduler thread."""
    global _scheduler_thread, _scheduler_stop_event
    
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("Workflow scheduler already running")
        return
    
    _scheduler_stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_run_scheduler,
        args=(db_manager,),
        daemon=True,
        name="WorkflowSchedulerV2"
    )
    _scheduler_thread.start()
    logger.info("Started workflow scheduler v2")


def stop_workflow_scheduler() -> None:
    """Stop the background workflow scheduler thread."""
    global _scheduler_thread, _scheduler_stop_event
    
    if not _scheduler_thread:
        return
    
    logger.info("Stopping workflow scheduler v2...")
    _scheduler_stop_event.set()
    _scheduler_thread.join(timeout=10)
    _scheduler_thread = None
    logger.info("Workflow scheduler v2 stopped")


def _run_scheduler(db_manager: DatabaseManager) -> None:
    """Main scheduler loop - checks for due workflows and runs them."""
    logger.info("Workflow scheduler v2 started")
    
    while not _scheduler_stop_event.is_set():
        try:
            _check_and_run_due_workflows(db_manager)
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
        
        # Sleep for 30 seconds between checks
        _scheduler_stop_event.wait(30)
    
    logger.info("Workflow scheduler v2 exiting")


def _check_and_run_due_workflows(db_manager: DatabaseManager) -> None:
    """Check for workflows that are due to run and execute them."""
    try:
        # Get all active scheduled workflows
        workflows = db_manager.get_active_scheduled_workflows()
        
        for workflow in workflows:
            if _scheduler_stop_event.is_set():
                break
            
            if _is_workflow_due(workflow):
                logger.info(f"Workflow {workflow.id} ({workflow.name}) is due, executing...")
                _execute_workflow_async(db_manager, workflow)
    except Exception as e:
        logger.error(f"Error checking due workflows: {e}", exc_info=True)


def _is_workflow_due(workflow) -> bool:
    """Check if a workflow is due to run based on its schedule."""
    if workflow.schedule_type != 'interval':
        return False
    
    schedule_config = workflow.schedule_config or {}
    interval_seconds = schedule_config.get('interval_seconds', 3600)
    
    if not workflow.last_run_at:
        # Never run before - it's due
        return True
    
    next_run_time = workflow.last_run_at + timedelta(seconds=interval_seconds)
    return datetime.utcnow() >= next_run_time


def _execute_workflow_async(db_manager: DatabaseManager, workflow) -> None:
    """Execute a workflow in a separate thread."""
    try:
        from workflows.workflow_engine import WorkflowExecutionEngine
        
        # Create engine with workflow owner's user_id
        engine = WorkflowExecutionEngine(db_manager, workflow.owner_user_id)
        
        # Run the workflow
        result = asyncio.run(engine.execute_workflow(workflow.id))
        
        if result.get('status') == 'completed':
            logger.info(f"Scheduled workflow {workflow.id} completed successfully")
        else:
            logger.warning(f"Scheduled workflow {workflow.id} finished with status: {result.get('status')}")
            
    except Exception as e:
        logger.error(f"Error executing scheduled workflow {workflow.id}: {e}", exc_info=True)


def reconcile_scheduler_state(db_manager: DatabaseManager) -> None:
    """Ensure scheduler is running if there are active scheduled workflows."""
    try:
        workflows = db_manager.get_active_scheduled_workflows()
        
        if workflows:
            start_workflow_scheduler(db_manager)
        else:
            # No active scheduled workflows, stop scheduler if running
            if _scheduler_thread and _scheduler_thread.is_alive():
                logger.info("No active scheduled workflows, scheduler will continue but idle")
    except Exception as e:
        logger.error(f"Error reconciling scheduler state: {e}", exc_info=True)
