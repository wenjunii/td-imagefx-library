layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uAmountX;
uniform float uAmountY;
uniform float uMidpoint;
uniform float uMapScale;

void main()
{
    vec2 uv = vUV.st;
    vec2 mapUV = fract((uv - 0.5) * max(uMapScale, 0.001) + 0.5);
    vec2 displacement = texture(sTD2DInputs[1], mapUV).rg - vec2(uMidpoint);
    vec2 sampleUV = clamp(uv + displacement * vec2(uAmountX, uAmountY), vec2(0.0), vec2(1.0));

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], sampleUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
