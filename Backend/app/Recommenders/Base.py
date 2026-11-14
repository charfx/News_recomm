from abc import ABC, abstractmethod

class BaseRecommender(ABC):
    name = "base"
    @abstractmethod
    def fit(self, news): ...                          # apprendre sur le corpus
    @abstractmethod
    def recommend(self, news_id, k=10): ...           # k articles proches