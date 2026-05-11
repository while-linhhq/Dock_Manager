from __future__ import annotations

import torch


class ReidEmbeddingNet(torch.nn.Module):
    def __init__(self, embedding_dim: int = 512) -> None:
        super().__init__()
        from torchvision import models

        base = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        in_features = base.fc.in_features
        base.fc = torch.nn.Identity()
        self.backbone = base
        self.head = torch.nn.Linear(in_features, embedding_dim)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        features = self.backbone(images)
        embeddings = self.head(features)
        return torch.nn.functional.normalize(embeddings, p=2, dim=1)
