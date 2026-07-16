uniform float uMix;
uniform float uMode;
uniform float uThreshold;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 repaired = source;
    float mode = floor(uMode + 0.5);
    if (mode < 0.5) {
        repaired.rgb *= step(uThreshold, source.a);
    } else if (mode < 1.5) {
        repaired.rgb *= source.a;
    } else {
        repaired.rgb = source.a > uThreshold ? source.rgb / source.a : vec3(0.0);
    }
    fragColor = TDOutputSwizzle(mix(source, repaired, clamp(uMix, 0.0, 1.0)));
}
