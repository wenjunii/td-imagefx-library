layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uWarmth;
uniform float uFade;
uniform float uContrast;
uniform float uPaper;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    float luma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    vec3 chroma = source.rgb - vec3(luma);
    vec3 warmScale = vec3(1.0 + 0.22 * uWarmth, 1.0 + 0.04 * uWarmth, 1.0 - 0.28 * uWarmth);
    vec3 faded = vec3(luma) + chroma * (1.0 - clamp(uFade, 0.0, 1.0));
    vec3 toned = faded * max(warmScale, vec3(0.0)) + vec3(uPaper, uPaper * 0.72, uPaper * 0.34);
    toned = (toned - vec3(0.5)) * max(uContrast, 0.0) + vec3(0.5);
    vec4 effect = vec4(max(toned, vec3(0.0)), source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
