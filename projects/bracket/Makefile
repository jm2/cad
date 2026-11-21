# Targets: build render check export slice roundtrip view all clean
#          asm exploded draft overhang print slice-print   (assemblies / mfg)
# Vars:    SECTION=y=0  RENDER_ARGS=--annotate  PRINTER=X1C|H2D  FILAMENT="Bambu PLA Basic"
#          PROCESS="0.20mm Standard"  CHECK_ARGS=
NAME     := bracket
CAD      ?= $(abspath ../..)
PY       := $(CAD)/.venv/bin/python
export PYTHONPATH := $(CAD)
export VTK_DEFAULT_OPENGL_WINDOW := vtkEGLRenderWindow
OUT      := out
STEP     := $(OUT)/$(NAME).step
SRC      := $(filter-out test_%.py,$(wildcard *.py))
PRINTER  ?= X1C
FILAMENT ?= Bambu PLA Basic
PROCESS  ?= 0.20mm Standard
SECTION  ?= y=0
RENDER_ARGS ?= --annotate
CHECK_ARGS  ?= --wall --min-wall $(shell $(PY) -c 'import params; print(getattr(params,"MIN_WALL",0.8))') --density $(shell $(PY) -c 'import params; print(getattr(params,"DENSITY",1.24))')

.PHONY: all build render check test export slice roundtrip view clean \
        asm exploded draft overhang print slice-print
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
	$(PY) -m tools.slice $(OUT)/$(NAME).stl -o $(OUT)/slice \
	  --printer "$(PRINTER)" --filament "$(FILAMENT)" --process "$(PROCESS)"

roundtrip: $(STEP)
	$(PY) -m tools.roundtrip $(STEP)

view:
	$(PY) model.py

asm:            # pairwise interference / clearance + per-part validity
	$(PY) -m tools.assembly model.py --per-part

exploded:
	$(PY) -m tools.render model.py -o $(OUT)/renders --name $(NAME) --views iso,iso_below --exploded

draft:          # moulding: draft + undercuts per part (PULL in model.py)
	$(PY) -m tools.mfg draft model.py -o $(OUT)/mfg --name $(NAME) $(if $(SECTION),--section $(SECTION))

overhang:       # FDM: support-needing area per part (PRINT_ORIENT in model.py)
	$(PY) -m tools.mfg overhang model.py -o $(OUT)/mfg --name $(NAME)

print:          # per-part print-oriented meshes
	$(PY) -m tools.export model.py --print -o $(OUT)/print --formats stl,3mf

slice-print: print
	$(PY) -m tools.slice $(OUT)/print/*.stl -o $(OUT)/slice-print \
	  --printer "$(PRINTER)" --filament "$(FILAMENT)" --process "$(PROCESS)"

clean:
	rm -rf $(OUT)
