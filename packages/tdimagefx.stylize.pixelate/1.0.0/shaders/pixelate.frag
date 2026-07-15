layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uPixelSize;

void main()
{
    vec2 uv = vUV.st;
    vec2 resolution = uTD2DInfos[0].res.zw;
    vec2 cells = max(vec2(1.0), resolution / max(uPixelSize, 1.0));
    vec2 pixelUV = (floor(uv * cells) + 0.5) / cells;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], pixelUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
