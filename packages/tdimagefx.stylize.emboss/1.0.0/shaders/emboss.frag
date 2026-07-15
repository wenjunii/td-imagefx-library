layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAngle;
uniform float uDistance;
uniform float uStrength;
uniform float uBias;
uniform float uColorAmount;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 texel = vec2(1.0) / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 direction = vec2(cos(uAngle), sin(uAngle)) * max(uDistance, 0.0) * texel;
    vec3 forwardSample = texture(sTD2DInputs[0], uv + direction).rgb;
    vec3 backwardSample = texture(sTD2DInputs[0], uv - direction).rgb;
    vec3 difference = (forwardSample - backwardSample) * uStrength;
    float relief = dot(difference, vec3(0.2126, 0.7152, 0.0722)) + uBias;
    vec3 grayscaleRelief = vec3(relief);
    vec3 colorRelief = source.rgb + difference;
    vec3 embossed = mix(grayscaleRelief, colorRelief, clamp(uColorAmount, 0.0, 1.0));
    vec4 effect = vec4(embossed, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
