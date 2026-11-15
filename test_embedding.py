from Backend.app.data_loader import load_user_events
from Backend.app.Recommenders.Embedding import EmbeddingRecommender

rec = EmbeddingRecommender()
events = load_user_events(1)
profile = rec.build_user_profile(events)
print(rec.recommend_for_user(profile, events["news_id"].tolist()).to_string())