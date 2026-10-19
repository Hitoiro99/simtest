import math
from common.expression import evaluate
from solvers.exceptions import ConfigurationError
from common.units import convert, parse


def statistics(errors, samples):
    volumes = [sample["volume"] for sample in samples]
    if not errors or any(not math.isfinite(v) or v <= 0 for v in volumes) or any(not math.isfinite(e) for e in errors):
        return None
    total = sum(volumes)
    maximum = max(range(len(errors)), key=errors.__getitem__)
    return {
        "mean": sum(v * e for v, e in zip(volumes, errors)) / total,
        "rms": math.sqrt(sum(v * e * e for v, e in zip(volumes, errors)) / total),
        "max": errors[maximum],
        "max_position": samples[maximum]["center"],
        "max_cell_id": samples[maximum]["cell_id"],
    }


def field_comparisons(context, datasets):
    results = []
    for ref_id, reference in context.condition.get("references", {}).items():
        if "field" not in reference:
            continue
        field = reference["field"]
        unit = context.case["fields"][field].get("unit", "")
        output_scale, _ = parse(unit)
        scale = reference["reference_scale"]
        scale_value = convert(scale["value"], scale.get("unit", unit), unit)
        parameters = {
            name: float(value["value"]) * parse(value.get("unit"))[0]
            for name, value in reference.get("parameters", {}).items()
        }
        expressions = reference["expression"]
        vector = isinstance(expressions, dict)
        if vector:
            components = list("xyz") + ["magnitude"]
        else:
            components = ["scalar"]
        for dataset in datasets:
            if (dataset["field"], dataset["domain"]) != (field, reference["domain"]):
                continue
            errors = {component: [] for component in components}
            normalized = {component: [] for component in components}
            for sample in dataset["samples"]:
                values = [float(v) for v in sample["value"]]
                env = dict(parameters)
                env.update(zip("xyz", sample["center"]))
                env["t"] = dataset["time"]
                try:
                    if vector:
                        exact = [evaluate(expressions[c], env) / output_scale for c in "xyz"]
                    else:
                        exact = [evaluate(expressions, env) / output_scale]
                except ConfigurationError:
                    exact = [float("nan")] * len(values)
                if vector:
                    values += [math.sqrt(sum(v * v for v in values))]
                    exact += [math.sqrt(sum(v * v for v in exact))]
                for component, value, target in zip(components, values, exact):
                    error = abs(value - target)
                    errors[component].append(error)
                    normalized[component].append(error / max(abs(target), scale_value))
            for component in components:
                absolute = statistics(errors[component], dataset["samples"])
                relative = statistics(normalized[component], dataset["samples"])
                available = absolute is not None and relative is not None
                results.append(
                    {
                        "reference_id": ref_id,
                        "field": field,
                        "domain": dataset["domain"],
                        "time": dataset["time"],
                        "component": component,
                        "status": "AVAILABLE" if available else "UNAVAILABLE",
                        "unit": unit,
                        "absolute_error": absolute,
                        "normalized_error": relative,
                        "reference_scale": scale_value,
                        "expression": expressions,
                        "parameters": reference.get("parameters", {}),
                        "source": reference["source"],
                        "reason": None if available else "无效场值或体积；未丢弃单元",
                    }
                )
    return results


def monitor_comparisons(context):
    results = []
    for ref_id, reference in context.condition.get("references", {}).items():
        if "monitor" not in reference:
            continue
        name = reference["monitor"]
        declaration = context.case["monitors"][name]
        unit = declaration.get("unit", "")
        records = context.manifest["monitors"][name]
        last = max(records, key=lambda record: (record["step"], record["time"] or 0))
        value = float(last["value"])
        target = convert(reference["value"], reference.get("unit", unit), unit)
        scale = reference["reference_scale"]
        scale_value = convert(scale["value"], scale.get("unit", unit), unit)
        available = math.isfinite(value) and last["quality"] == "valid"
        if available:
            error = abs(value - target)
            normalized_error = error / max(abs(target), scale_value)
        else:
            error = None
            normalized_error = None
        results.append(
            {
                "reference_id": ref_id,
                "monitor": name,
                "step": last["step"],
                "time": last["time"],
                "value": value,
                "reference_value": target,
                "unit": unit,
                "absolute_error": error,
                "normalized_error": normalized_error,
                "status": "AVAILABLE" if available else "UNAVAILABLE",
                "source": reference["source"],
            }
        )
    return results
