layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAmount;
uniform float uSoftness;
uniform float uRoundness;
uniform vec4 uColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 p = abs(uv - 0.5) * 2.0;
    float exponent = max(0.25, uRoundness) * 2.0;
    float distanceToCenter = pow(pow(p.x, exponent) + pow(p.y, exponent), 1.0 / exponent);
    float edge = smoothstep(1.0 - max(uSoftness, 0.001), 1.0, distanceToCenter);
    float strength = clamp(abs(uAmount), 0.0, 1.0) * edge * clamp(uColor.a, 0.0, 1.0);
    vec3 darkened = mix(source.rgb, uColor.rgb, strength);
    vec3 lightened = mix(source.rgb, vec3(1.0) - (vec3(1.0) - source.rgb) * (vec3(1.0) - uColor.rgb), strength);
    vec3 result = uAmount >= 0.0 ? darkened : lightened;
    vec4 effect = vec4(result, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
