uniform float uMix;
uniform float uLeft;
uniform float uRight;
uniform float uBottom;
uniform float uTop;
uniform float uFeather;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float leftEdge = min(uLeft, uRight);
    float rightEdge = max(uLeft, uRight);
    float bottomEdge = min(uBottom, uTop);
    float topEdge = max(uBottom, uTop);
    float feather = max(uFeather, 0.000001);
    float horizontal = smoothstep(leftEdge, leftEdge + feather, uv.x)
        * (1.0 - smoothstep(rightEdge - feather, rightEdge, uv.x));
    float vertical = smoothstep(bottomEdge, bottomEdge + feather, uv.y)
        * (1.0 - smoothstep(topEdge - feather, topEdge, uv.y));
    float matte = horizontal * vertical;
    vec4 cropped = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, cropped, clamp(uMix, 0.0, 1.0)));
}
