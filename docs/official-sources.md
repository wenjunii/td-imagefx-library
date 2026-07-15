# Official sources

These links are the primary references for TouchDesigner behavior used by TD ImageFX Library. They are intentionally linked rather than copied because Derivative updates documentation and release notes as builds change.

## TouchDesigner releases and fundamentals

- [TouchDesigner User Guide](https://docs.derivative.ca/Main_Page) — current documentation entry point and build notices.
- [TouchDesigner downloads](https://derivative.ca/download) — Official and Experimental installers.
- [TouchDesigner Release Notes](https://docs.derivative.ca/Release_Notes) — build changes, known issues, and backward-compatibility notes. The updater may monitor this as a discovery source, but a release note never authorizes automatic package activation.
- [Getting Started](https://docs.derivative.ca/Getting_started) — projects, operators, saving, media, and Operator Snippets.
- [TouchDesigner glossary](https://docs.derivative.ca/TouchDesigner_Glossary) — canonical operator and workflow terminology.

## Image processing and GLSL

- [TOP overview](https://docs.derivative.ca/TOP) — TouchDesigner's texture/image operator family.
- [Feedback TOP](https://docs.derivative.ca/Feedback_TOP) — retained-frame target, reset, and feedback-loop behavior used by temporal and simulation effects.
- [GLSL TOP](https://docs.derivative.ca/GLSL_TOP) — shader node modes, parameters, inputs, outputs, formats, and performance information.
- [Write a GLSL TOP](https://docs.derivative.ca/Write_a_GLSL_TOP) — input sampling, `vUV`, built-in samplers and texture info, uniforms, output swizzling, compute shaders, and debugging guidance.
- [GLSL category](https://docs.derivative.ca/Category:GLSL) — related shader documentation.
- [Texture Sampling Parameters](https://docs.derivative.ca/Texture_Sampling_Parameters) — filtering, extension behavior, and sampling settings.
- [Pixel Formats](https://docs.derivative.ca/Pixel_Formats) — texture channel storage and precision choices.
- [Color Space](https://docs.derivative.ca/Color_Space) — project working space and image/color conversion behavior.

TouchDesigner's GLSL guide links to the [Khronos OpenGL Shading Language specification registry](https://registry.khronos.org/OpenGL/index_gl.php), the upstream language specification. TouchDesigner-specific built-ins and supported versions still come from Derivative's documentation.

## Components, parameters, and Python

- [Component](https://docs.derivative.ca/Component) — component networks and saving reusable `.tox` files.
- [.tox files](https://docs.derivative.ca/.tox) — reusable TouchDesigner component file format.
- [COMP Generator Common Page](https://docs.derivative.ca/COMP_Generator_Common_Page) — external `.tox`, reload, backup, and relative-path behavior shared by generator components.
- [Parameter](https://docs.derivative.ca/Parameter) — built-in and custom parameter concepts and types.
- [Custom Parameters](https://docs.derivative.ca/Custom_Parameters) — authoring component interfaces.
- [Extensions](https://docs.derivative.ca/Extensions) — Python extension lifecycle, access, initialization, and cleanup.
- [Introduction to Python Tutorial](https://docs.derivative.ca/Introduction_to_Python_Tutorial) — TouchDesigner Python environment and operator access.
- [OP Class](https://docs.derivative.ca/OP_Class) and [COMP Class](https://docs.derivative.ca/COMP_Class) — scripting APIs used by integration/build tooling.
- [TOP Class](https://docs.derivative.ca/TOP_Class) — texture-operator scripting, dimensions, format, memory, cook, and timing information used by diagnostics and benchmarks.
- [Virtual File System](https://docs.derivative.ca/Virtual_File_System) — embedding package assets into a component when a release chooses that distribution model.

## Animation, control, and timing

- [CHOP overview](https://docs.derivative.ca/CHOP) — channel data used for animation, audio, logic, and device input.
- [Export](https://docs.derivative.ca/Export) — driving parameters from CHOP channels.
- [Binding](https://docs.derivative.ca/Binding) — parameter binding and dependencies.
- [Animation COMP](https://docs.derivative.ca/Animation_COMP) — keyframe animation data.
- [Absolute Time](https://docs.derivative.ca/Absolute_Time) — project-independent time values and frame/second relationships relevant to deterministic animation controls.
- [LFO CHOP](https://docs.derivative.ca/LFO_CHOP) — cyclic modulation.
- [Audio Spectrum CHOP](https://docs.derivative.ca/Audio_Spectrum_CHOP) — audio-reactive frequency analysis.
- [MIDI In CHOP](https://docs.derivative.ca/MIDI_In_CHOP) — MIDI control input.
- [OSC In CHOP](https://docs.derivative.ca/OSC_In_CHOP) — OSC control input.

## Performance and diagnostics

- [Info DAT](https://docs.derivative.ca/Info_DAT) — operator warnings, errors, and other diagnostic data.
- [Info CHOP](https://docs.derivative.ca/Info_CHOP) — operator cook/performance channels.
- [Perform CHOP](https://docs.derivative.ca/Perform_CHOP) — FPS, frame time, dropped frames, memory, and process state.
- [Perform DAT](https://docs.derivative.ca/Perform_DAT) — detailed performance logging.
- [Performance Monitor](https://docs.derivative.ca/Performance_Monitor) — operator cook analysis and CPU/GPU performance investigation.
- [Optimize](https://docs.derivative.ca/Optimize) — official optimization guidance.
- [Engine COMP](https://docs.derivative.ca/Engine_COMP) — loading `.tox` files in TouchEngine when process separation is appropriate.

## Official community and support

- [Derivative forum](https://forum.derivative.ca/) — official community discussions, announcements, and troubleshooting. Forum content is useful discovery material but is not equivalent to product documentation or a redistribution license.
- [Derivative tutorials](https://derivative.ca/community) — official community and learning entry point.
- [Derivative support service](https://derivative.ca/support-service) — current support, forum, bug-report, account, and licensing routes.

## Source-use policy

When adding an external effect, shader, plugin, or technique:

1. Link the exact original page/repository and author.
2. Record the license; absence of a license does not grant redistribution rights.
3. Distinguish factual documentation, inspiration, adapted code, and vendored code.
4. Preserve required notices and disclose modifications.
5. Prefer official documentation for APIs and build compatibility.
6. Re-check upstream source and release dates during package updates.

This page is a reference index, not an allow-list of packages or publishers.
