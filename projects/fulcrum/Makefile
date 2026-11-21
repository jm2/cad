# Fulcrum: ambidextrous wired/wireless mouse.
#   make <target> VARIANT=molded|fdm      (default molded)
# Targets: build render exploded sections check test asm draft overhang
#          export print slice roundtrip mass view all clean
VARIANT  ?= molded
NAME     := fulcrum_$(VARIANT)
CAD      ?= $(abspath ../..)
PY       := $(CAD)/.venv/bin/python
export PYTHONPATH := $(CAD)
export FULCRUM_VARIANT := $(VARIANT)
export VTK_DEFAULT_OPENGL_WINDOW := vtkEGLRenderWindow
OUT      := out/$(VARIANT)
STEP     := $(OUT)/$(NAME).step
SRC      := params.py form.py layout.py top.py base.py wheel.py model.py
PRINTER  ?= X1C
FILAMENT ?= Bambu PLA Basic
PROCESS  ?= 0.20mm Standard
SHELLS   := top_shell,base,btn_left,btn_right,door

.PHONY: all build render exploded sections check test asm draft overhang export \
        print slice roundtrip mass view clean

all: build render check

build: $(STEP)
$(STEP): $(SRC)
	$(PY) -m tools.export model.py -o $(OUT) --name $(NAME) --formats step

render: build
	$(PY) -m tools.render model.py -o $(OUT)/renders --name $(NAME) \
	  --views iso,top,right,back,iso_back,bottom

exploded: build
	$(PY) -m tools.render model.py -o $(OUT)/renders --name $(NAME) \
	  --views iso,iso_below --exploded

sections: build
	$(PY) -m tools.render model.py -o $(OUT)/renders --name $(NAME)_x0 --views iso --section x=0
	$(PY) -m tools.render model.py -o $(OUT)/renders --name $(NAME)_x14 --views iso --section x=14
	$(PY) -m tools.render model.py -o $(OUT)/renders --name $(NAME)_y33 --views iso --section y=33

test:
	$(PY) -m pytest -q -s test_model.py

asm:
	$(PY) -m tools.assembly model.py

check: test asm

draft:
	$(PY) -m tools.mfg draft model.py --part top_shell -o $(OUT)/mfg --name $(NAME) --section x=0
	$(PY) -m tools.mfg draft model.py --part base -o $(OUT)/mfg --name $(NAME) --pull 0,0,-1 --section x=0

overhang:
	for p in top_shell base door btn_left btn_right; do \
	  $(PY) -m tools.mfg overhang model.py --part $$p -o $(OUT)/mfg --name $(NAME) || true; done

export: build
	$(PY) -m tools.export model.py -o $(OUT) --name $(NAME)

print:
	$(PY) -m tools.export model.py --print -o $(OUT)/print --formats stl,3mf \
	  --only $(SHELLS),btn_mode,btn_dpi_up,btn_dpi_down,btn_side_l1,btn_side_l2,btn_side_r1,btn_side_r2,wheel_core,yoke

slice: print
	$(PY) -m tools.slice $(OUT)/print/*.stl -o $(OUT)/slice \
	  --printer "$(PRINTER)" --filament "$(FILAMENT)" --process "$(PROCESS)" --set enable_support=1

roundtrip: build
	$(PY) -m tools.roundtrip $(STEP)

mass:
	$(PY) mass.py

view:
	$(PY) -c "import model; from ocp_vscode import show; p = model.build(); show(*p.values(), names=list(p))"

clean:
	rm -rf out/$(VARIANT)
