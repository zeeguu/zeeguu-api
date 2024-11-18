from zeeguu.core.model import Topic, UrlKeyword, NewTopic
from zeeguu.core.model.article import article_topic_map
from zeeguu.core.model.article_url_keyword_map import ArticleUrlKeywordMap
from zeeguu.core.model.new_article_topic_map import TopicOriginType, NewArticleTopicMap
from zeeguu.core.model.difficulty_lingo_rank import DifficultyLingoRank
from elasticsearch import Elasticsearch
from zeeguu.core.elastic.settings import ES_CONN_STRING, ES_ZINDEX
from zeeguu.core.semantic_vector_api import get_embedding_from_article


def find_topics(article_id, session):
    article_topic = (
        session.query(Topic)
        .join(article_topic_map)
        .filter(article_topic_map.c.article_id == article_id)
    )
    topics = ""
    for t in article_topic:
        topics = topics + str(t.title) + " "

    return topics.rstrip()


def find_new_topics(article_id, session):
    article_topics = (
        session.query(NewTopic)
        .join(NewArticleTopicMap)
        .filter(NewArticleTopicMap.article_id == article_id)
        .filter(NewArticleTopicMap.origin_type != TopicOriginType.INFERRED.value)
        .all()
    )
    inferred_article_topics = (
        session.query(NewTopic)
        .join(NewArticleTopicMap)
        .filter(NewArticleTopicMap.article_id == article_id)
        .filter(NewArticleTopicMap.origin_type == TopicOriginType.INFERRED.value)
        .all()
    )
    return article_topics, inferred_article_topics


def find_filter_url_keywords(article_id, session):
    article_url_keywords = (
        session.query(UrlKeyword)
        .join(ArticleUrlKeywordMap)
        .filter(ArticleUrlKeywordMap.article_id == article_id)
    )
    topic_kewyords = [
        str(t_key.keyword)
        for t_key in article_url_keywords
        if t_key not in UrlKeyword.EXCLUDE_TOPICS
    ]
    return topic_kewyords


def document_from_article(article, session, is_v7=True, current_doc=None):
    old_topics = find_topics(article.id, session)

    if is_v7:
        print("## Warning: Version for ES is 7, using old indexing system...")
        doc = {
            "title": article.title,
            "author": article.authors,
            "content": article.content,
            "summary": article.summary,
            "word_count": article.word_count,
            "published_time": article.published_time,
            "topics": old_topics,
            "language": article.language.name,
            "fk_difficulty": article.fk_difficulty,
            "lr_difficulty": DifficultyLingoRank.value_for_article(article),
            "url": article.url.as_string(),
            "video": article.video,
        }
    else:
        topics, topics_inferred = find_new_topics(article.id, session)
        embedding_generation_required = current_doc is None
        # Embeddings only need to be re-computed if the document
        # doesn't exist or the text is updated.
        # This is the most expensive operation in the indexing process, so it
        # saves time by skipping it.
        if current_doc is not None:
            embedding_generation_required = current_doc["content"] != article.content
        doc = {
            "title": article.title,
            "author": article.authors,
            "content": article.content,
            "summary": article.summary,
            "word_count": article.word_count,
            "published_time": article.published_time,
            "old_topics": old_topics,
            "topics": [t.title for t in topics],
            # We need to avoid using these as a way to classify further documents
            # (we should rely on the human labels to classify further articles)
            # rather than infer on inferences.
            "topics_inferred": [t.title for t in topics_inferred],
            "language": article.language.name,
            "fk_difficulty": article.fk_difficulty,
            "lr_difficulty": DifficultyLingoRank.value_for_article(article),
            "url": article.url.as_string(),
            "video": article.video,
        }
        if not embedding_generation_required and current_doc is not None:
            doc["sem_vec"] = current_doc["sem_vec"]
        else:
            doc["sem_vec"] = get_embedding_from_article(article)

    return doc


def create_or_update(article, session):
    es = Elasticsearch(ES_CONN_STRING)
    es_version = int(es.info()["version"]["number"][0])
    doc = document_from_article(article, session, is_v7=es_version == 7)

    if es.exists(index=ES_ZINDEX, id=article.id):
        es.delete(index=ES_ZINDEX, id=article.id)

    res = es.index(index=ES_ZINDEX, id=article.id, body=doc)

    return res


def create_or_update_doc_for_bulk(article, session):
    es = Elasticsearch(ES_CONN_STRING)
    es_version = int(es.info()["version"]["number"][0])

    doc = {}
    doc["_id"] = article.id
    doc["_index"] = ES_ZINDEX
    if es.exists(index=ES_ZINDEX, id=article.id):
        current_doc = es.get(index=ES_ZINDEX, id=article.id)
        doc_data = document_from_article(
            article, session, is_v7=es_version == 7, current_doc=current_doc["_source"]
        )
        doc["_op_type"] = "update"
        doc["_source"] = {"doc": doc_data}
    else:
        doc_data = document_from_article(article, session, is_v7=es_version == 7)
        doc["_op_type"] = "create"
        doc["_source"] = doc_data
    return doc


def index_in_elasticsearch(new_article, session):
    """
    # Saves the news article at ElasticSearch.
    # We recommend that everything is stored both in SQL and Elasticsearch
    # as ElasticSearch isn't persistent data
    """
    try:
        es = Elasticsearch(ES_CONN_STRING)
        es_version = int(es.info()["version"]["number"][0])
        doc = document_from_article(new_article, session, is_v7=es_version == 7)
        res = es.index(index=ES_ZINDEX, id=new_article.id, document=doc)

    except Exception as e:
        import traceback

        traceback.print_exc()


def remove_from_index(article):
    es = Elasticsearch(ES_CONN_STRING)
    if es.exists(index=ES_ZINDEX, id=article.id):
        print("Found in ES Index")
        es.delete(index=ES_ZINDEX, id=article.id)
        print("After deletion from the index.")
