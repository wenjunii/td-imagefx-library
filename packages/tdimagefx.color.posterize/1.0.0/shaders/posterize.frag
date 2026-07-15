layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uLevels;
uniform float uGamma;

void main()
{
    vec4 source = texture(sTD2DInputs[0], vUV.st);
    float levels = max(2.0, floor(uLevels + 0.5));
    float gamma = max(0.001, uGamma);
    vec3 linearized = pow(max(source.rgb, vec3(0.0)), vec3(gamma));
    vec3 quantized = floor(linearized * (levels - 1.0) + 0.5) / (levels - 1.0);
    quantized = pow(max(quantized, vec3(0.0)), vec3(1.0 / gamma));
    vec4 effect = vec4(quantized, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
