.PHONY: doc
doc: Doxyfile
	doxygen Doxyfile

.PHONY: clean
clean:
	rm -rf doc/*

.PHONY: set_version
ifdef VERSION
set_version: Doxyfile
	@echo "[i] Version of this Project will set to '${VERSION}'"
	sed -i "s/PROJECT_NUMBER\s*= .*/PROJECT_NUMBER         = ${VERSION}/g" Doxyfile 
	@echo "[i] Consider making a git tag"
else
set_version:
	@echo "Usage: make VERSION=12.3 set_version"
	@false
endif
