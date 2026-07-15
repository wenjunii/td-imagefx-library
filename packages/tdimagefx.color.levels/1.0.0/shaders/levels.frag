layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uInputBlack;
uniform float uInputWhite;
uniform float uGamma;
uniform float uOutputBlack;
uniform float uOutputWhite;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    float inputRange = max(uInputWhite - uInputBlack, 0.00001);
    vec3 normalized = clamp((source.rgb - vec3(uInputBlack)) / inputRange, 0.0, 1.0);
    vec3 corrected = pow(normalized, vec3(1.0 / max(uGamma, 0.00001)));
    vec3 mapped = mix(vec3(uOutputBlack), vec3(uOutputWhite), corrected);
    vec4 effect = vec4(mapped, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
