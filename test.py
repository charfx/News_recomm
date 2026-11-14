from Backend.app.data_loader import load_news
from Backend.app.Recommenders.Tf_IDF import TfidfRecommender

news = load_news()
model = TfidfRecommender().fit(news)
print(model.X.shape)
print(news.loc[0, "Title"])
print(model.recommend("N55528", k=5))