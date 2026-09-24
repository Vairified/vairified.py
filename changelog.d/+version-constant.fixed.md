`vairified.__version__` now tracks the released version. It had read `"0.5.0"`
against a tagged `v0.7.0` — two minors stale — because `pyproject.toml` and `__init__.py` are
two separate version sources and only one of them was being bumped. Anything reporting the SDK
version at runtime, such as a support diagnostic, was naming a release from two versions back.
