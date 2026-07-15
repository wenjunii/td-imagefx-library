layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uHorizontal;
uniform float uVertical;
uniform float uSeamX;
uniform float uSeamY;

void main()
{
    vec2 uv = vUV.st;
    vec2 mirroredUV = uv;
    float foldedX = uSeamX - abs(uv.x - uSeamX);
    float foldedY = uSeamY - abs(uv.y - uSeamY);
    mirroredUV.x = mix(uv.x, foldedX, step(0.5, uHorizontal));
    mirroredUV.y = mix(uv.y, foldedY, step(0.5, uVertical));
    mirroredUV = clamp(mirroredUV, vec2(0.0), vec2(1.0));

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], mirroredUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
