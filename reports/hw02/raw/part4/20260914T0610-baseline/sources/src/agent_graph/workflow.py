"""Compile the actual LangGraph supervisor workflow."""

from langgraph.graph import END, START, StateGraph

from .nodes import planner_node, reviewer_node, supervisor_node
from .router import router_logic
from .state import AgentState, create_initial_state


def recursion_limit(max_turns: int) -> int:
    """Allow initial supervisor + worker/supervisor pairs and terminal headroom."""

    if type(max_turns) is not int or max_turns < 1:
        raise ValueError("max_turns must be a positive integer")
    return 2 * max_turns + 10


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor", router_logic,
        {"planner": "planner", "reviewer": "reviewer", END: END},
    )
    graph.add_edge("planner", "supervisor")
    graph.add_edge("reviewer", "supervisor")
    return graph.compile()
