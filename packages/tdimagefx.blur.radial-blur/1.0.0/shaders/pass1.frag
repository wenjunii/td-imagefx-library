layout(location = 0) out vec4 fragColor;

uniform float uStrength;
uniform float uCenterX;
uniform float uCenterY;

void main()
{
    vec2 uv = vUV.st;
    vec2 centerUv = vec2(uCenterX, uCenterY);
    vec2 ray = uv - centerUv;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 sum = vec3(0.0);
    for (int i = 0; i < 8; ++i)
    {
        float t = float(i) / 7.0;
        vec2 sampleUv = clamp(uv - ray * max(uStrength, 0.0) * t, vec2(0.0), vec2(1.0));
        sum += texture(sTD2DInputs[0], sampleUv).rgb;
    }
    fragColor = TDOutputSwizzle(vec4(sum * 0.125, source.a));
}
