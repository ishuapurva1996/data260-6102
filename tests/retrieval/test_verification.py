import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('verify_part2',Path(__file__).resolve().parents[2]/'scripts/verify_hw03_part2.py')
verify=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def test_vector_recomputation_detects_corruption():
    record={'query_embedding_dimension':2,'query_embedding_first8':[1.,0.],
            'query_vector_shape':[2], 'document_vector_shape':[1,2], 'returned_k':1,
            'hits':[{'cosine':1.,'rank':1}]}
    vectors={'query':[1.,0.],'documents':[[1.,0.]]}
    verify.validate_record_vectors(record,vectors)
    vectors['documents']=[[0.,1.]]
    with pytest.raises(ValueError,match='cosine'):
        verify.validate_record_vectors(record,vectors)


def test_vector_shape_is_checked():
    record={'query_embedding_dimension':2,'query_embedding_first8':[1.,0.],
            'query_vector_shape':[2], 'document_vector_shape':[3,2], 'returned_k':1,
            'hits':[{'cosine':1.,'rank':1}]}
    with pytest.raises(ValueError,match='shape'):
        verify.validate_record_vectors(record,{'query':[1.,0.],'documents':[[1.,0.]]})


def test_campaign_must_match_frozen_query_gold_config():
    from copy import deepcopy
    questions=[{'id':'Q1','question':'Frozen question','expected_source_ids':['gold'],'designation':'baseline'}]
    config={'high_score_threshold':.5,'k':3,'repeats':10,'warmup_searches':1}
    run={'config':config,'questions':questions}
    record={**questions[0],'question_id':'Q1','requested_k':3,'search_seconds':[.001]*10,'unmeasured_warmup_searches':1}
    verify.validate_campaign_contract(run,[record],questions,config)
    for field,value in [('question','different'),('expected_source_ids',['wrong']),('requested_k',2)]:
        bad=deepcopy(record); bad[field]=value
        with pytest.raises(ValueError):
            verify.validate_campaign_contract(run,[bad],questions,config)
    bad=deepcopy(run); bad['config']['k']=4
    with pytest.raises(ValueError,match='config'):
        verify.validate_campaign_contract(bad,[record],questions,config)


def test_node_inventory_rejects_corrupt_aggregate():
    nodes=[{'node_id':'n','source_id':'s','indexed_text':'abc','context_text':'abc'}]
    stats={'chunk_count':1,'max_seq_length':256,'node_lengths':[{'node_id':'n','source_id':'s','character_length':3,'context_character_length':3,'token_length':4,'context_token_length':4,'truncated':False}],
           'average_character_length':3.,'average_token_length':4.,'average_context_character_length':3.,'average_context_token_length':4.,
           'indexed_truncation_count':0,'indexed_truncation_fraction':0.,'semantic_buffers':[],
           'semantic_buffer_count':0,'semantic_buffer_truncation_count':0,'semantic_buffer_truncation_fraction':0.}
    verify.validate_node_inventory(nodes,stats)
    stats['average_character_length']=99
    with pytest.raises(ValueError,match='average'):
        verify.validate_node_inventory(nodes,stats)
