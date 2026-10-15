"""Reproducible synthetic service benchmark; never opens real models or a DB."""
import argparse
import gc
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from time import perf_counter
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from app.domain.schemas import ModelManifest
from app.infrastructure.cached_predictor_provider import CachedPredictorProvider
from app.infrastructure.predictor_factory import PredictorFactory
from app.services.prediction_service import PredictionService


def rss_bytes():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb',wintypes.DWORD),('faults',wintypes.DWORD)] + [(name,ctypes.c_size_t) for name in
                ('peak','working','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile')]
        value = Counters(); value.cb = ctypes.sizeof(value)
        api = ctypes.windll.psapi.GetProcessMemoryInfo
        api.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if api(wintypes.HANDLE(-1), ctypes.byref(value), value.cb): return value.working
        return None
    path = Path('/proc/self/statm')
    return int(path.read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE') if path.exists() else None


def measure(folder, iterations, cached):
    manifest = ModelManifest.model_validate({**json.loads((folder / 'metadata.json').read_text()), 'model_path':folder})
    class Catalog:
        def get(self, model_id): return manifest
    class History:
        def add(self, record): pass
    provider = CachedPredictorProvider(PredictorFactory(), max_entries=4 if cached else 0)
    service = PredictionService(Catalog(), provider, History())
    rows = [{f'x{index}':float(index + row)/10 for index in range(8)} for row in range(16)]
    gc.collect(); baseline = rss_bytes(); tracemalloc.start()
    durations, checksums, observed_rss = [], [], []
    for _ in range(iterations + 1):
        gc.collect()
        started = perf_counter()
        result = service.predict_json(manifest.id, rows)
        durations.append((perf_counter() - started) * 1000)
        checksums.append(sum(row['prediction'] for row in result.records))
        current = rss_bytes()
        if current is not None: observed_rss.append(current)
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    assert len(set(checksums)) == 1
    return {'mode':'cached' if cached else 'uncached', 'first_ms':round(durations[0],3),
            'p50_ms':round(float(np.percentile(durations[1:],50)),3),
            'p95_ms':round(float(np.percentile(durations[1:],95)),3), 'iterations':iterations,
            'rss_baseline_bytes':baseline, 'rss_after_bytes':rss_bytes(),
            'max_observed_rss_bytes':max(observed_rss) if observed_rss else None,
            'python_traced_peak_bytes':peak, 'cache':provider.info(), 'prediction_checksum':checksums[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations',type=int,default=30)
    parser.add_argument('--folder',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--mode',choices=['cached','uncached'],help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 5 <= args.iterations <= 200: parser.error('iterations must be 5–200')
    if args.folder:
        print(json.dumps(measure(args.folder,args.iterations,args.mode == 'cached'))); return
    with tempfile.TemporaryDirectory(prefix='edgeml-cache-benchmark-') as temporary:
        folder = Path(temporary)
        rng = np.random.default_rng(42)
        frame = pd.DataFrame(rng.normal(size=(1600,8)),columns=[f'x{i}' for i in range(8)])
        model = RandomForestRegressor(n_estimators=120,max_depth=12,random_state=42,n_jobs=1).fit(frame,frame.x0*2-frame.x1)
        joblib.dump(model,folder/'model.pkl')
        manifest = ModelManifest(id='synthetic',name='synthetic',version='1.0.0',framework='sklearn',problem_type='regression',
            target='target',features=[{'name':name,'dtype':'float64'} for name in frame],author='benchmark',
            created_at='2026-10-15',description='synthetic benchmark',model_path=folder)
        (folder/'metadata.json').write_text(manifest.model_dump_json(),encoding='utf-8')
        reports=[]
        for mode in ('uncached','cached'):
            output = subprocess.run([sys.executable,__file__,'--folder',str(folder),'--mode',mode,'--iterations',str(args.iterations)],
                check=True,capture_output=True,text=True)
            reports.append(json.loads(output.stdout))
        assert reports[0]['prediction_checksum'] == reports[1]['prediction_checksum']
        print(json.dumps({'python':platform.python_version(),'platform':platform.system(),
            'artifact_bytes':(folder/'model.pkl').stat().st_size,'scope':'direct PredictionService; no HTTP/network or disk history',
            'notes':'Separate processes per mode. Timings include tracemalloc; observed RSS is not a hard memory limit.',
            'results':reports},indent=2))


if __name__ == '__main__': main()
