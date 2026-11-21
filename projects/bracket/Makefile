# Targets: build render check export slice roundtrip view all clean
# Vars:    SECTION=y=0   RENDER_ARGS=--annotate   PROFILE=path.ini   CHECK_ARGS=
NAME     := bracket
CAD      ?= $(abspath ../..)
PY       := $(CAD)/.venv/bin/python
export PYTHONPATH := $(CAD)
export VTK_DEFAULT_OPENGL_WINDOW := vtkEGLRenderWindow
OUT      := out
STEP     := $(OUT)/$(NAME).step
SRC      := $(filter-out test_%.py,$(wildcard *.py))
PROFILE  ?= $(CAD)/tools/profiles/generic_pla_0.4.ini
SECTION  ?= y=0
RENDER_ARGS ?= --annotate
CHECK_ARGS  ?= --wall --min-wall $(shell $(PY) -c 'import params; print(getattr(params,"MIN_WALL",0.8))') --density $(shell $(PY) -c 'import params; print(getattr(params,"DENSITY",1.24))')

.PHONY: all build render check test export slice roundtrip view clean
all: build render check

build: $(STEP)
$(STEP): $(SRC)
	$(PY) -m tools.build model.py -o $(OUT) --name $(NAME)

render: $(STEP)
	$(PY) -m tools.render $(STEP) -o $(OUT)/renders --name $(NAME) \
	  $(if $(SECTION),--section $(SECTION)) $(RENDER_ARGS)

check: $(STEP) test
	$(PY) -m tools.check $(STEP) $(CHECK_ARGS)

test:
	$(PY) -m pytest -q -s test_model.py

export: $(STEP)
	$(PY) -m tools.export model.py -o $(OUT) --name $(NAME)

slice: export
	$(PY) -m tools.slice $(OUT)/$(NAME).stl --profile $(PROFILE) -o $(OUT)/$(NAME).gcode

roundtrip: $(STEP)
	$(PY) -m tools.roundtrip $(STEP)

view:
	$(PY) model.py

clean:
	rm -rf $(OUT)
