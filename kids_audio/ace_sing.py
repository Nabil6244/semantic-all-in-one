"""Sung kids songs with ACE-Step 1.5 (local, free; https://github.com/ace-step/ACE-Step-1.5, installed in ~/ace-step-1.5).

Run with ACE-Step's own Python (it has its own environment):
    ~/ace-step-1.5/.venv/bin/python kids_audio/ace_sing.py job.json
job = {"caption": "cheerful preschool nursery song, ...", "lyrics": "[verse]\\n...", "bpm": 100, "duration": 45,
       "out": "song.wav", "seed": 7, "batch": 1}
Models download into ACE-Step's checkpoints folder the first time. Prints {"files": [...], "seconds": s}.
"""
import json
import os
import shutil
import sys
import time

ACE = os.path.expanduser("~/ace-step-1.5")
sys.path.insert(0, ACE)


def main(job):
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler
    from acestep.model_downloader import ensure_main_model, get_checkpoints_dir

    os.chdir(ACE)                                   # ACE-Step finds its checkpoints from its own folder
    ck = get_checkpoints_dir()
    ok, msg = ensure_main_model(ck)
    if not ok:
        raise RuntimeError(msg)
    t = time.time()
    dit, llm = AceStepHandler(), LLMHandler()
    # 16 GB Mac: the MLX copy of the singer runs on the GPU; the PyTorch copy waits in RAM (offload), or MPS runs out
    dit.initialize_service(project_root=ACE, config_path="acestep-v15-turbo", device="mps", use_mlx_dit=True,
                           offload_to_cpu=job.get("offload", True), offload_dit_to_cpu=job.get("offload", True))
    # 0.6B planner by default: the 1.7B one ran out of GPU memory on a 16 GB Mac (11.7 GB MPS + 10 GB other)
    lm = job.get("lm", "acestep-5Hz-lm-0.6B")
    from acestep.model_downloader import ensure_lm_model
    ensure_lm_model(lm, ck)
    llm.initialize(checkpoint_dir=str(ck), lm_model_path=lm, backend="mlx", device="mps")
    params = GenerationParams(caption=job["caption"], lyrics=job["lyrics"], bpm=job.get("bpm"),
                              duration=job.get("duration", -1), vocal_language="en", inference_steps=8, shift=3.0,
                              seed=job.get("seed", -1))
    cfg = GenerationConfig(batch_size=job.get("batch", 1), audio_format="wav", use_random_seed="seed" not in job,
                           seeds=[job["seed"]] if "seed" in job else None)
    out_dir = os.path.dirname(os.path.abspath(job["out"]))
    os.makedirs(out_dir, exist_ok=True)
    res = generate_music(dit, llm, params, cfg, save_dir=out_dir)
    if not res.success:
        raise RuntimeError(res.error)
    files = []
    base, ext = os.path.splitext(job["out"])
    for i, a in enumerate(res.audios):
        dst = job["out"] if i == 0 else f"{base}_{i}{ext}"
        shutil.move(a["path"], dst)
        files.append(dst)
    print(json.dumps({"files": files, "seconds": round(time.time() - t, 1)}))


if __name__ == "__main__":
    main(json.load(open(os.path.abspath(sys.argv[1]))))
