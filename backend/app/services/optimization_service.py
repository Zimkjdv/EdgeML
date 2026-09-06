import math
import numpy as np
import pandas as pd
from app.domain.model_catalog import ModelCatalog
from app.domain.optimization import OptimizationRequest, OptimizationResult, PredictorProvider, Recommendation
from app.domain.errors import PredictionValidationError


class OptimizationService:
    """Bounded mixed-variable evolutionary search through the predictor boundary."""
    def __init__(self, catalog: ModelCatalog, factory: PredictorProvider, population=256, iterations=12, defaults=None):
        self.catalog, self.factory = catalog, factory
        self.population, self.iterations = population, iterations
        self.defaults = defaults

    def feature_defaults(self, model_id: str):
        manifest = self.catalog.get(model_id)
        return self.defaults.get(manifest) if self.defaults else {'origin':'unavailable', 'dataset_id':None, 'features':{}}

    def run(self, request: OptimizationRequest) -> OptimizationResult:
        manifest = self.catalog.get(request.model_id)
        if manifest.problem_type != 'regression':
            raise PredictionValidationError('Optimization currently supports regression models only.')
        rules = {p.name: p for p in request.parameters}
        if len(rules) != len(request.parameters) or set(rules) != {f.name for f in manifest.features}:
            raise PredictionValidationError('Provide exactly one rule for every model feature.')
        if not any(p.optimize for p in request.parameters):
            raise PredictionValidationError('Select at least one parameter to optimize.')
        domains = []
        for feature in manifest.features:
            p = rules[feature.name]
            numeric = feature.dtype.startswith(('int', 'float'))
            integer = feature.dtype.startswith('int')
            if not p.optimize:
                if p.value is None or (isinstance(p.value, str) and (not p.value.strip() or len(p.value) > 1000)):
                    raise PredictionValidationError(f'{p.name}: a fixed value is required.')
                if numeric:
                    try:
                        value = float(p.value)
                    except (ValueError, TypeError):
                        raise PredictionValidationError(f'{p.name}: fixed value must be numeric.')
                    if not math.isfinite(value) or (integer and not value.is_integer()):
                        raise PredictionValidationError(f'{p.name}: invalid fixed numeric value.')
                    domains.append(('fixed', int(value) if integer else value))
                else:
                    domains.append(('fixed', p.value))
            elif numeric:
                if p.minimum is None or p.maximum is None or p.minimum >= p.maximum:
                    raise PredictionValidationError(f'{p.name}: minimum must be less than maximum.')
                if not math.isfinite(p.maximum-p.minimum):
                    raise PredictionValidationError(f'{p.name}: numeric range is too large.')
                step = p.step or (1 if integer else None)
                if integer and (not p.minimum.is_integer() or not p.maximum.is_integer() or not float(step).is_integer()):
                    raise PredictionValidationError(f'{p.name}: integer features require integer bounds and step.')
                if step and (step > p.maximum-p.minimum or (p.maximum-p.minimum)/step > 1e9):
                    raise PredictionValidationError(f'{p.name}: invalid step size.')
                domains.append(('numeric', p.minimum, p.maximum, step, integer))
            else:
                choices = list(dict.fromkeys(p.choices))
                if not choices or any(not c.strip() or len(c) > 1000 for c in choices):
                    raise PredictionValidationError(f'{p.name}: provide allowed categories.')
                domains.append(('category', choices))
        rng = np.random.default_rng(request.seed)
        predictor = self.factory.create(manifest)
        names = [f.name for f in manifest.features]
        seen, scored, history = set(), [], []
        for iteration in range(self.iterations):
            rows = []
            elites = scored[:max(1, self.population//8)]
            for _ in range(self.population):
                parent = elites[int(rng.integers(len(elites)))][2] if elites and rng.random() < .7 else None
                row = []
                for j, domain in enumerate(domains):
                    if domain[0] == 'fixed':
                        value = domain[1]
                    elif domain[0] == 'category':
                        value = parent[j] if parent and rng.random() < .6 else domain[1][int(rng.integers(len(domain[1])))]
                    else:
                        _, low, high, step, integer = domain
                        value = float(np.clip(rng.normal(parent[j], (high-low)*(.25/(iteration+1)**.5)), low, high)) if parent else float(rng.uniform(low, high))
                        if step:
                            index = min(math.floor((high-low)/step), max(0, round((value-low)/step)))
                            value = low + index*step
                        value = int(round(value)) if integer else float(value)
                    row.append(value)
                key = tuple(row)
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
            if not rows:
                break
            predictions = np.asarray(predictor.predict(pd.DataFrame(rows, columns=names)), dtype=float).reshape(-1)
            if len(predictions) != len(rows) or not np.isfinite(predictions).all():
                raise PredictionValidationError('The model returned invalid predictions.')
            scored.extend((abs(float(y)-request.target), float(y), row) for row, y in zip(rows, predictions))
            scored.sort(key=lambda item: item[0])
            history.append(scored[0][0])
        # Prefer meaningfully different combinations, then fill with distinct
        # candidates if the feasible space is too small for that separation.
        selected = []
        def distance(a, b):
            return max([abs(a[j]-b[j])/(d[2]-d[1]) if d[0]=='numeric' else float(a[j]!=b[j])
                        for j, d in enumerate(domains) if d[0]!='fixed'], default=0)
        for threshold in (.03, 0):
            for item in scored:
                if len(selected) == request.count:
                    break
                if all(distance(item[2], old[2]) > threshold for old in selected):
                    selected.append(item)
        selected.sort(key=lambda item: item[0])
        return OptimizationResult(model_id=manifest.id, model_name=manifest.name, target=request.target,
            tolerance=request.tolerance, seed=request.seed, evaluated=len(seen), best_error_by_iteration=history,
            recommendations=[Recommendation(parameters=dict(zip(names, row)), prediction=y,
                absolute_error=error, within_tolerance=error <= request.tolerance) for error,y,row in selected])
