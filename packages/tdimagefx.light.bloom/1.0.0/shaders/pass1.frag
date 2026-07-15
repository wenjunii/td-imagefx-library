layout(location = 0) out vec4 fragColor;

uniform float uThreshold;
uniform float uSoftKnee;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float brightness = max(source.r, max(source.g, source.b));
    float threshold = max(uThreshold, 0.0);
    float knee = max(uSoftKnee, 0.001);
    float soft = clamp((brightness - threshold + knee) / (2.0 * knee), 0.0, 1.0);
    soft = soft * soft * knee;
    float contribution = max(brightness - threshold, soft) / max(brightness, 0.0001);
    fragColor = TDOutputSwizzle(vec4(source.rgb * contribution, source.a));
}
