"""index_dataset 骨架占位：验收 slug=dataset_index；行为用例于 fn-implement 阶段填充。"""
from src.index_dataset.index_dataset import index_dataset


def test_dataset_index_skeleton():
    assert callable(index_dataset)
