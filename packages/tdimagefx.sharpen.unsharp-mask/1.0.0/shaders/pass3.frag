layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAmount;
uniform float uThreshold;

void main()
{
    vec2 uv = vUV.st;
    vec3 blurred = texture(sTD2DInputs[0], uv).rgb;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 detail = original.rgb - blurred;
    float magnitude = max(abs(detail.r), max(abs(detail.g), abs(detail.b)));
    float gate = smoothstep(max(uThreshold, 0.0), max(uThreshold, 0.0) + 0.01, magnitude);
    vec3 sharpened = original.rgb + detail * max(uAmount, 0.0) * gate;
    vec3 result = mix(original.rgb, sharpened, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
