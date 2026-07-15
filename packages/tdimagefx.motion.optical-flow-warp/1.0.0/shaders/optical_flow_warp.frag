uniform float uMix; uniform float uScale; uniform float uConfidence; uniform float uFlipY;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv); vec4 field = texture(sTD2DInputs[1], uv);
    vec2 flow = field.rg * 2.0 - 1.0; flow.y *= mix(1.0,-1.0,step(.5,uFlipY)); float confidence = mix(1.0, field.b, uConfidence);
    vec4 warped = texture(sTD2DInputs[0], uv - flow * uScale * confidence);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, warped.rgb, clamp(uMix,0.0,1.0)), src.a));
}
