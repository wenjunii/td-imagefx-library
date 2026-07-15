layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uExposure;
uniform float uOffset;
uniform float uContrast;
uniform float uPivot;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    vec3 exposed = source.rgb * exp2(uExposure) + vec3(uOffset);
    vec3 graded = (exposed - vec3(uPivot)) * max(uContrast, 0.0) + vec3(uPivot);
    vec4 effect = vec4(max(graded, vec3(0.0)), source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
