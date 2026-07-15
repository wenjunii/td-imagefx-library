layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uStrength;
uniform float uCenterX;
uniform float uCenterY;

void main()
{
    vec2 uv = vUV.st;
    vec2 centerUv = vec2(uCenterX, uCenterY);
    vec2 ray = uv - centerUv;
    vec4 original = texture(sTD2DInputs[1], uv);
    vec3 sum = vec3(0.0);
    for (int i = 0; i < 8; ++i)
    {
        float t = float(i) / 7.0;
        vec2 sampleUv = clamp(uv - ray * max(uStrength, 0.0) * 0.5 * t, vec2(0.0), vec2(1.0));
        sum += texture(sTD2DInputs[0], sampleUv).rgb;
    }
    vec3 blurred = sum * 0.125;
    vec3 result = mix(original.rgb, blurred, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(result, original.a));
}
