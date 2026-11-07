"""The two helpers the OpenVoice tone-colour converter needs, without librosa/soundfile (MIT, from myshell-ai/OpenVoice)."""
import json

import torch

_hann: dict = {}


class HParams:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, HParams(**v) if isinstance(v, dict) else v)

    def __getitem__(self, key):
        return getattr(self, key)

    def keys(self):
        return self.__dict__.keys()

    def items(self):
        return self.__dict__.items()

    def values(self):
        return self.__dict__.values()


def hparams_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return HParams(**json.loads(f.read()))


def spectrogram_torch(y, n_fft, sampling_rate, hop_size, win_size, center=False):
    key = f"{win_size}_{y.dtype}_{y.device}"
    if key not in _hann:
        _hann[key] = torch.hann_window(win_size).to(dtype=y.dtype, device=y.device)
    pad = int((n_fft - hop_size) / 2)
    y = torch.nn.functional.pad(y.unsqueeze(1), (pad, pad), mode="reflect").squeeze(1)
    spec = torch.stft(y, n_fft, hop_length=hop_size, win_length=win_size, window=_hann[key], center=center,
                      pad_mode="reflect", normalized=False, onesided=True, return_complex=False)
    return torch.sqrt(spec.pow(2).sum(-1) + 1e-6)
