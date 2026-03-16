"""LangGraph pipeline: wire up all agents into a StateGraph."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.approval import approval_agent
from src.agents.fraud import fraud_detection_agent
from src.agents.ingestion import ingestion_agent
from src.agents.payment import payment_agent
from src.agents.state import PipelineState
from src.agents.validation import validation_agent


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("ingestion", ingestion_agent)
    graph.add_node("validation", validation_agent)
    graph.add_node("fraud_detection", fraud_detection_agent)
    graph.add_node("approval", approval_agent)
    graph.add_node("payment", payment_agent)

    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "validation")
    graph.add_edge("validation", "fraud_detection")
    graph.add_edge("fraud_detection", "approval")
    graph.add_edge("approval", "payment")
    graph.add_edge("payment", END)

    return graph


def compile_graph():
    graph = build_graph()
    return graph.compile()


def run_pipeline(file_path: str) -> Dict[str, Any]:
    """Run the full pipeline on a single invoice file."""
    app = compile_graph()

    initial_state: PipelineState = {
        "file_path": file_path,
        "raw_text": "",
        "invoice": None,
        "validation_result": None,
        "fraud_result": None,
        "approval_result": None,
        "payment_result": None,
        "processing_log": [],
        "errors": [],
    }

    result = app.invoke(initial_state)
    return result
