"""Train and export the compact beacon-candidate CNN."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def _training_modules():
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, Dataset, random_split
    except ImportError as exc:
        raise RuntimeError(
            "training requires PyTorch; install requirements-training.txt"
        ) from exc
    return torch, nn, DataLoader, Dataset, random_split


def train_model(
    dataset_dir: str | Path = "training/dataset",
    output_onnx_path: str | Path = "tracking/model.onnx",
    *,
    checkpoint_path: str | Path = "tracking/model.pt",
    epochs: int = 10,
    batch_size: int = 32,
    seed: int = 42,
) -> dict[str, float]:
    """Train with a deterministic validation split and export an ONNX model."""
    if epochs <= 0 or batch_size <= 0:
        raise ValueError("epochs and batch_size must be > 0")

    torch, nn, DataLoader, Dataset, random_split = _training_modules()

    class PatchDataset(Dataset):
        def __init__(self, root: Path) -> None:
            self.samples = [
                *((path, 1.0) for path in sorted((root / "positive").glob("*.png"))),
                *((path, 0.0) for path in sorted((root / "negative").glob("*.png"))),
            ]

        def __len__(self) -> int:
            return len(self.samples)

        def __getitem__(self, index: int):
            path, label = self.samples[index]
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise RuntimeError(f"failed to read training patch: {path}")
            image = cv2.resize(image, (32, 32), interpolation=cv2.INTER_AREA)
            tensor = torch.from_numpy(image.astype(np.float32) / 255.0).unsqueeze(0)
            return tensor, torch.tensor([label], dtype=torch.float32)

    class BeaconPatchCNN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(1, 8, 3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Conv2d(8, 12, 3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),
                nn.Conv2d(12, 16, 3, padding=1),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d(1),
            )
            self.classifier = nn.Linear(16, 1)

        def forward(self, inputs):
            return self.classifier(self.features(inputs).flatten(1))

    dataset = PatchDataset(Path(dataset_dir))
    if len(dataset) < 10:
        raise ValueError("dataset must contain at least 10 patches")

    torch.manual_seed(seed)
    validation_size = max(2, round(len(dataset) * 0.2))
    train_size = len(dataset) - validation_size
    train_data, validation_data = random_split(
        dataset,
        [train_size, validation_size],
        generator=torch.Generator().manual_seed(seed),
    )
    train_loader = DataLoader(
        train_data,
        batch_size=batch_size,
        shuffle=True,
        generator=torch.Generator().manual_seed(seed),
    )
    validation_loader = DataLoader(validation_data, batch_size=batch_size)

    model = BeaconPatchCNN()
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    final_loss = 0.0

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(inputs), labels)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
        final_loss = total_loss / max(len(train_loader), 1)
        print(f"Epoch {epoch + 1:02d}/{epochs}: loss={final_loss:.4f}")

    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for inputs, labels in validation_loader:
            predictions = torch.sigmoid(model(inputs)) >= 0.5
            correct += int((predictions == (labels >= 0.5)).sum().item())
            total += labels.numel()
    validation_accuracy = correct / max(total, 1)

    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_shape": (1, 1, 32, 32),
            "validation_accuracy": validation_accuracy,
        },
        checkpoint,
    )

    output = Path(output_onnx_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    dummy_input = torch.zeros((1, 1, 32, 32), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        str(output),
        input_names=["patch"],
        output_names=["logit"],
        opset_version=17,
        dynamo=False,
    )
    print(f"Validation accuracy: {validation_accuracy * 100.0:.2f}%")
    print(f"ONNX model exported to {output}")
    return {"loss": final_loss, "validation_accuracy": validation_accuracy}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="training/dataset")
    parser.add_argument("--output", default="tracking/model.onnx")
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()
    train_model(args.dataset, args.output, epochs=args.epochs)