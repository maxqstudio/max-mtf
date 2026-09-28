from __future__ import annotations

"""Static authority contract for Scientist Python's exposed analytical surface.

This module intentionally contains *no* scientific imports.  It is imported by both the
host validator and the dedicated child so that generated Scientist code sees one governed
capability vocabulary.  The child maps these names to proxy objects; raw numpy/pandas/
scipy/sklearn module objects are never placed in generated-code globals.
"""

ALLOWED_IMPORTS = frozenset({
    "math",
    "statistics",
    "json",
    "numpy",
    "pandas",
    "scipy",
    "scipy.stats",
    "sklearn",
    "sklearn.metrics",
    "sklearn.preprocessing",
    "sklearn.model_selection",
    "sklearn.linear_model",
    "sklearn.cluster",
})

# Attribute names that generated code may use on plain in-memory Python values or on
# capability proxies/wrappers.  Any other attribute is rejected by the host validator.
# Raw scientific/native module objects are never exposed, so this is an allowlist rather
# than a denylist layered on top of unrestricted modules.
SAFE_ATTRIBUTE_NAMES = frozenset({
    # plain containers / strings
    "get", "keys", "values", "items", "copy", "count", "index", "append", "extend",
    "insert", "pop", "remove", "sort", "reverse", "lower", "upper", "strip", "lstrip",
    "rstrip", "split", "rsplit", "join", "startswith", "endswith", "replace",
    # math/statistics/json capability functions
    "sqrt", "log", "log1p", "log2", "log10", "exp", "expm1", "fabs", "floor", "ceil",
    "isfinite", "isnan", "isinf", "mean", "fmean", "median", "median_low", "median_high",
    "pstdev", "pvariance", "stdev", "variance", "quantiles", "correlation", "linear_regression",
    "dumps", "loads",
    # numpy capability surface
    "array", "asarray", "std", "var", "sum", "min", "max", "percentile", "quantile",
    "corrcoef", "cov", "abs", "clip", "where", "unique", "argsort", "argmax", "argmin",
    "concatenate", "stack", "vstack", "hstack", "linspace", "arange", "dot", "diff",
    "cumsum", "cumprod", "round", "zeros", "ones", "full", "random", "choice", "permutation",
    "normal", "uniform", "integers",
    # safe array wrapper
    "tolist", "to_list", "reshape", "flatten", "ravel", "astype", "shape", "size", "ndim",
    "dtype",
    # pandas capability / wrappers
    "DataFrame", "Series", "head", "tail", "to_dict", "to_numpy", "sort_values", "dropna",
    "fillna", "assign", "describe", "nunique", "value_counts", "corr", "groupby", "agg",
    # scipy.stats capability
    "pearsonr", "spearmanr", "ttest_ind", "mannwhitneyu", "zscore", "normaltest", "sem",
    # sklearn capability
    "metrics", "preprocessing", "model_selection", "linear_model", "cluster",
    "mean_squared_error", "mean_absolute_error", "r2_score", "accuracy_score",
    "StandardScaler", "train_test_split", "LinearRegression", "KMeans",
    "fit", "predict", "score", "transform", "fit_transform", "coef_", "intercept_", "cluster_centers_",
})

# Explicitly documented dangerous/transitive names.  SAFE_ATTRIBUTE_NAMES is the actual
# authority; this set exists for acceptance scanning, diagnostics, and defense in depth.
TRANSITIVE_DANGEROUS_ATTRIBUTES = frozenset({
    "ctypes", "ctypeslib", "CDLL", "PyDLL", "WinDLL", "OleDLL", "windll", "oledll",
    "pythonapi", "data", "base", "__array_interface__", "__array_struct__", "mmap", "memmap",
    "load_library", "system", "popen", "spawn", "socket", "connect", "open", "read_csv",
    "read_html", "to_csv", "to_pickle", "load", "save", "fromfile", "tofile",
})

SAFE_IMPORT_SURFACE = {
    "math": frozenset({"sqrt", "log", "log1p", "log2", "log10", "exp", "expm1", "fabs", "floor", "ceil", "isfinite", "isnan", "isinf"}),
    "statistics": frozenset({"mean", "fmean", "median", "median_low", "median_high", "pstdev", "pvariance", "stdev", "variance", "quantiles", "correlation", "linear_regression"}),
    "json": frozenset({"dumps", "loads"}),
    "numpy": frozenset({"array", "asarray", "mean", "median", "std", "var", "sum", "min", "max", "percentile", "quantile", "corrcoef", "cov", "sqrt", "log", "log1p", "exp", "abs", "clip", "where", "isnan", "isfinite", "unique", "argsort", "argmax", "argmin", "concatenate", "stack", "vstack", "hstack", "linspace", "arange", "dot", "diff", "cumsum", "cumprod", "round", "zeros", "ones", "full", "random"}),
    "pandas": frozenset({"DataFrame", "Series"}),
    "scipy": frozenset({"stats"}),
    "scipy.stats": frozenset({"pearsonr", "spearmanr", "ttest_ind", "mannwhitneyu", "zscore", "describe", "normaltest", "sem"}),
    "sklearn": frozenset({"metrics", "preprocessing", "model_selection", "linear_model", "cluster"}),
    "sklearn.metrics": frozenset({"mean_squared_error", "mean_absolute_error", "r2_score", "accuracy_score"}),
    "sklearn.preprocessing": frozenset({"StandardScaler"}),
    "sklearn.model_selection": frozenset({"train_test_split"}),
    "sklearn.linear_model": frozenset({"LinearRegression"}),
    "sklearn.cluster": frozenset({"KMeans"}),
}


def capability_surface_manifest() -> dict[str, list[str]]:
    return {name: sorted(values) for name, values in sorted(SAFE_IMPORT_SURFACE.items())}
