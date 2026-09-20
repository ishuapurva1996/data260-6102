"""Build one independent, local, in-memory index per chunking technique."""


def build_index(nodes, embed_model):
    from llama_index.core import Settings, StorageContext, VectorStoreIndex
    from llama_index.core.schema import MetadataMode
    from llama_index.core.vector_stores import SimpleVectorStore

    if embed_model is None:
        raise ValueError("An explicit local embedding model is required")
    for node in nodes:
        if node.get_content(metadata_mode=MetadataMode.EMBED) != node.text:
            raise ValueError(f"Embedding metadata is not excluded for node {node.node_id}")
        if node.embedding is not None:
            raise ValueError(f"Node {node.node_id} already has an unaudited embedding")
    Settings.llm = None
    storage_context = StorageContext.from_defaults(vector_store=SimpleVectorStore())
    return VectorStoreIndex(nodes, storage_context=storage_context,
                            embed_model=embed_model, show_progress=False)
