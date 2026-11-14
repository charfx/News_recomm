import numpy as np
from Backend.app.data_loader import load_news, load_user_events
from Backend.app.Recommenders.Tf_IDF import TfidfRecommender, build_user_profile

news = load_news().reset_index(drop=True)      # lignes numérotées 0, 1, 2...
rec = TfidfRecommender().fit(news)

events = load_user_events(1)
profile = build_user_profile(events, rec.X, rec.index.to_dict())

words = rec.vectorizer.get_feature_names_out()
top = np.argsort(profile)[::-1][:15]
print("Mots du profil :", [words[i] for i in top])
recos = rec.recommend_for_user(profile, events["news_id"].tolist())
print(recos.to_string())