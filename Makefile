.PHONY: all dataset render generate validate export report test clean

SEED ?= 42

all: dataset

dataset:
	python -m driftbench all --seed $(SEED)

render:
	python -m driftbench render

generate:
	python -m driftbench generate --seed $(SEED)

validate:
	python -m driftbench validate

export:
	python -m driftbench export --seed $(SEED)

report:
	python -m driftbench report --seed $(SEED)

test:
	pytest

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('dataset').glob('*') if p.is_dir()]"
